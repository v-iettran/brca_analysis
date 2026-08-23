"""Build the committed human-development compound registry.

Reads optional local ChEMBL / DrugCentral extracts and LINCS compoundinfo,
merges curated seed rows plus human-approved review decisions, and writes
versioned artifacts under outputs/compound_registry/.

Never contacts the network. Runtime analysis does not run this job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline_core.compound_registry import _row_from_mapping
from pipeline_core.compound_registry_seed import seed_records
from pipeline_core.config import (
    COMPOUND_REGISTRY_DIR,
    COMPOUND_REGISTRY_MANIFEST,
    COMPOUND_REGISTRY_PARQUET,
    COMPOUND_REGISTRY_PATH,
    COMPOUND_REGISTRY_VERSION,
    COMPOUND_REVIEW_QUEUE_DIR,
    FINAL_PROJECT_ROOT,
)
from pipeline_core.drug_names import normalize_drug_name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_optional_table(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    if path.suffix == ".json":
        return pd.DataFrame(json.loads(path.read_text()))
    if path.suffix == ".parquet":
        return pd.DataFrame(pd.read_parquet(path))
    sep = "\t" if path.suffix in {".tsv", ".txt"} else ","
    return pd.read_csv(path, sep=sep)


def _merge_external(records: dict[str, dict], chembl: pd.DataFrame, drugcentral: pd.DataFrame) -> None:
    if not chembl.empty:
        name_col = next((c for c in ("pref_name", "canonical", "name") if c in chembl.columns), None)
        if name_col:
            for _, row in chembl.iterrows():
                canonical = normalize_drug_name(row[name_col])
                if not canonical or canonical not in records:
                    continue
                target = records[canonical]
                if "max_phase" in row and pd.notna(row["max_phase"]):
                    target["max_clinical_phase"] = float(row["max_phase"])
                if "withdrawn_flag" in row and bool(row["withdrawn_flag"]):
                    target["withdrawn_or_discontinued"] = True
                    target["entity_type"] = "withdrawn"
                    target["human_development_status"] = "withdrawn"
                    target["display_action"] = "technical_excluded"
                    target["display_gate_reason"] = "withdrawn_or_discontinued"
                if "chembl_id" in row and pd.notna(row["chembl_id"]):
                    ids = set(target.get("chembl_ids") or [])
                    ids.add(str(row["chembl_id"]))
                    target["chembl_ids"] = sorted(ids)
    if not drugcentral.empty:
        name_col = next((c for c in ("name", "canonical", "drug_name") if c in drugcentral.columns), None)
        if name_col:
            for _, row in drugcentral.iterrows():
                canonical = normalize_drug_name(row[name_col])
                if canonical in records and str(row.get("status", "")).upper() == "OFM":
                    records[canonical]["withdrawn_or_discontinued"] = True


def _load_approvals(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _apply_approvals(records: dict[str, dict], approvals: list[dict]) -> None:
    for decision in approvals:
        canonical = normalize_drug_name(decision["canonical"])
        row = _row_from_mapping({**records.get(canonical, {}), **decision})
        row["reviewed_by"] = decision.get("reviewer") or decision.get("reviewed_by")
        row["reviewed_at"] = decision.get("reviewed_at")
        records[canonical] = row


def _lincs_map(compoundinfo_path: Path, records: dict[str, dict]) -> list[dict]:
    if not compoundinfo_path.exists():
        return []
    info = pd.read_csv(compoundinfo_path, sep="\t")
    mapping = []
    name_col = "cmap_name" if "cmap_name" in info.columns else None
    if name_col is None:
        return []
    for _, row in info.iterrows():
        canonical = normalize_drug_name(row[name_col])
        if canonical not in records:
            continue
        pert_id = str(row.get("pert_id") or "")
        inchi = str(row.get("inchi_key") or "")
        if pert_id:
            ids = set(records[canonical].get("lincs_pert_ids") or [])
            ids.add(pert_id)
            records[canonical]["lincs_pert_ids"] = sorted(ids)
        if inchi and inchi not in {"", "nan"}:
            keys = set(records[canonical].get("inchi_keys") or [])
            keys.add(inchi)
            records[canonical]["inchi_keys"] = sorted(keys)
        mapping.append(
            {
                "canonical": canonical,
                "pert_id": pert_id,
                "inchi_key": inchi,
                "cmap_name": row[name_col],
            }
        )
    return mapping


def build_registry(
    chembl_path: Path | None = None,
    drugcentral_path: Path | None = None,
    compoundinfo_path: Path | None = None,
    approvals_path: Path | None = None,
) -> dict:
    records = {row["canonical"]: dict(row) for row in seed_records()}
    _merge_external(records, _load_optional_table(chembl_path), _load_optional_table(drugcentral_path))
    approvals_path = approvals_path or (COMPOUND_REVIEW_QUEUE_DIR / "approved_decisions.jsonl")
    _apply_approvals(records, _load_approvals(approvals_path))
    compoundinfo_path = compoundinfo_path or (FINAL_PROJECT_ROOT / "compoundinfo_beta.txt")
    pert_map = _lincs_map(compoundinfo_path, records)

    compounds = sorted(records.values(), key=lambda row: row["canonical"])
    COMPOUND_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "registry_version": COMPOUND_REGISTRY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "compounds": compounds,
    }
    COMPOUND_REGISTRY_PATH.write_text(json.dumps(payload, indent=2))
    pd.DataFrame(compounds).to_parquet(COMPOUND_REGISTRY_PARQUET, index=False)
    map_path = COMPOUND_REGISTRY_DIR / "lincs_pert_map.json"
    map_path.write_text(json.dumps(pert_map, indent=2))

    checksums = {
        COMPOUND_REGISTRY_PATH.name: _sha256(COMPOUND_REGISTRY_PATH),
        COMPOUND_REGISTRY_PARQUET.name: _sha256(COMPOUND_REGISTRY_PARQUET),
        map_path.name: _sha256(map_path),
    }
    manifest = {
        "registry_version": COMPOUND_REGISTRY_VERSION,
        "generated_at": payload["generated_at"],
        "n_compounds": len(compounds),
        "n_lincs_map_rows": len(pert_map),
        "sources": [
            {"name": "seed", "description": "Curated breast/oncology/tool snapshot"},
            {"name": "ChEMBL", "optional_extract": str(chembl_path) if chembl_path else None},
            {"name": "DrugCentral", "optional_extract": str(drugcentral_path) if drugcentral_path else None},
            {"name": "LINCS compoundinfo_beta", "path": str(compoundinfo_path)},
        ],
        "checksums": checksums,
        "note": "Display gating only. Does not alter Q4 / List 1 / List 2 ranks.",
    }
    COMPOUND_REGISTRY_MANIFEST.write_text(json.dumps(manifest, indent=2))
    (COMPOUND_REGISTRY_DIR.parent / "MANIFEST.sha256").write_text(
        "\n".join(f"{digest}  {name}" for name, digest in checksums.items()) + "\n"
    )
    from pipeline_core.compound_registry import load_manifest, load_registry

    load_registry.cache_clear()
    load_manifest.cache_clear()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chembl", type=Path, default=None)
    parser.add_argument("--drugcentral", type=Path, default=None)
    parser.add_argument("--compoundinfo", type=Path, default=None)
    parser.add_argument("--approvals", type=Path, default=None)
    args = parser.parse_args()
    manifest = build_registry(args.chembl, args.drugcentral, args.compoundinfo, args.approvals)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
