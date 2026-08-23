"""Versioned human-development-status registry for LINCS/Q4 compounds.

Runtime analysis never contacts ChEMBL, DrugCentral, or a research agent.
It only reads the committed, reviewed registry. Ranking is unchanged; this
module supplies lookup metadata for post-ranking display gating.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from pipeline_core.config import (
    COMPOUND_REGISTRY_MANIFEST,
    COMPOUND_REGISTRY_PARQUET,
    COMPOUND_REGISTRY_PATH,
    COMPOUND_REGISTRY_VERSION,
)
from pipeline_core.drug_names import normalize_drug_name

ENTITY_TYPES = (
    "approved_drug",
    "clinical_candidate",
    "preclinical_tool",
    "non_therapeutic_perturbagen",
    "withdrawn",
    "unresolved",
)

HUMAN_DEVELOPMENT_STATUSES = (
    "approved_breast",
    "approved_oncology",
    "approved_human_repurposing",
    "investigational",
    "withdrawn",
    "tool_compound",
    "non_drug_perturbagen",
    "unresolved",
)

DISPLAY_ACTIONS = ("default_visible", "exploratory_only", "technical_excluded")

ANONYMOUS_PERT_RE = re.compile(r"^(brd-|sa-)", re.IGNORECASE)

HUMAN_DEVELOPMENT_LABELS = {
    "approved_breast": "Approved drug (breast-cancer context)",
    "approved_oncology": "Approved oncology drug",
    "approved_human_repurposing": "Approved in humans (other indication)",
    "investigational": "Investigational / not approved",
    "withdrawn": "Withdrawn or discontinued",
    "tool_compound": "Research tool compound",
    "non_drug_perturbagen": "Non-therapeutic perturbagen",
    "unresolved": "Unresolved — pending curation",
}


def _row_from_mapping(item: dict) -> dict:
    canonical = normalize_drug_name(item.get("canonical") or item.get("display_name") or "")
    synonyms = [normalize_drug_name(s) for s in (item.get("synonyms") or []) if s]
    return {
        "canonical": canonical,
        "display_name": item.get("display_name") or canonical,
        "synonyms": synonyms,
        "lincs_pert_ids": list(item.get("lincs_pert_ids") or []),
        "inchi_keys": list(item.get("inchi_keys") or []),
        "chembl_ids": list(item.get("chembl_ids") or []),
        "drugcentral_ids": list(item.get("drugcentral_ids") or []),
        "entity_type": item.get("entity_type") or "unresolved",
        "max_clinical_phase": item.get("max_clinical_phase"),
        "human_development_status": item.get("human_development_status") or "unresolved",
        "breast_oncology_relevance": item.get("breast_oncology_relevance") or "unknown",
        "withdrawn_or_discontinued": bool(item.get("withdrawn_or_discontinued")),
        "display_action": item.get("display_action") or "technical_excluded",
        "display_gate_reason": item.get("display_gate_reason") or "unresolved_not_in_registry",
        "sources": list(item.get("sources") or []),
        "reviewed_by": item.get("reviewed_by"),
        "reviewed_at": item.get("reviewed_at"),
        "match_key": item.get("match_key") or "canonical",
    }


def _records_from_path(path: Path) -> list[dict]:
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        rows = data["compounds"] if isinstance(data, dict) and "compounds" in data else data
        return [_row_from_mapping(item) for item in rows]
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    return [_row_from_mapping(row) for row in frame.to_dict(orient="records")]


@lru_cache(maxsize=1)
def load_registry() -> pd.DataFrame:
    """Load the committed registry. Empty frame if artifacts are absent."""
    for path in (COMPOUND_REGISTRY_PATH, COMPOUND_REGISTRY_PARQUET):
        if path.exists():
            rows = _records_from_path(path)
            return pd.DataFrame(rows)
    return pd.DataFrame(columns=list(_row_from_mapping({}).keys()))


@lru_cache(maxsize=1)
def load_manifest() -> dict:
    if COMPOUND_REGISTRY_MANIFEST.exists():
        return json.loads(COMPOUND_REGISTRY_MANIFEST.read_text())
    return {
        "registry_version": COMPOUND_REGISTRY_VERSION,
        "n_compounds": int(len(load_registry())),
        "sources": [],
    }


def registry_version() -> str:
    return str(load_manifest().get("registry_version") or COMPOUND_REGISTRY_VERSION)


def _index_maps(frame: pd.DataFrame) -> dict[str, dict[str, dict]]:
    by_canonical: dict[str, dict] = {}
    by_pert: dict[str, dict] = {}
    by_inchi: dict[str, dict] = {}
    for row in frame.to_dict(orient="records"):
        by_canonical[row["canonical"]] = row
        for synonym in row.get("synonyms") or []:
            by_canonical.setdefault(synonym, row)
        for pert_id in row.get("lincs_pert_ids") or []:
            by_pert[str(pert_id).upper()] = row
        for inchi in row.get("inchi_keys") or []:
            by_inchi[str(inchi).upper()] = row
    return {"canonical": by_canonical, "pert": by_pert, "inchi": by_inchi}


def lookup_compound(
    name: str | None = None,
    pert_id: str | None = None,
    inchi_key: str | None = None,
) -> dict | None:
    """Prefer InChIKey, then LINCS pert_id, then canonical/synonym name."""
    frame = load_registry()
    if frame.empty:
        return None
    maps = _index_maps(frame)
    if inchi_key:
        hit = maps["inchi"].get(str(inchi_key).upper())
        if hit:
            return {**hit, "match_key": "inchi_key"}
    if pert_id:
        hit = maps["pert"].get(str(pert_id).upper())
        if hit:
            return {**hit, "match_key": "lincs_pert_id"}
    if name:
        hit = maps["canonical"].get(normalize_drug_name(name))
        if hit:
            return {**hit, "match_key": "canonical"}
    return None


def is_anonymous_perturbagen(name: str | None, pert_id: str | None = None) -> bool:
    for value in (name, pert_id):
        if value and ANONYMOUS_PERT_RE.match(str(value).strip()):
            return True
    return False


def human_development_label(status: str | None) -> str:
    return HUMAN_DEVELOPMENT_LABELS.get(status or "unresolved", HUMAN_DEVELOPMENT_LABELS["unresolved"])
