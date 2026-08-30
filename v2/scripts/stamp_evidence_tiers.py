#!/usr/bin/env python3
"""Attach evidence tiers to features and to reversal candidates.

Features are tiered from `data/reference/breast_evidence_sets.json`, a curated
file with named sources. Compounds are tiered from data already on disk:

  * `depmap_data/primary-screen-replicate-collapsed-treatment-info.csv` carries a
    real `phase` column (Launched / Phase 1-3 / Preclinical / Withdrawn) for
    4,518 compounds;
  * `compoundinfo_beta.txt` supplies target and mechanism of action;
  * `pipeline_core.nominations.BREAST_CONTEXT_DRUGS` and `clinical_comparators`
    are the curated breast standard-of-care lists.

Nothing is guessed. A compound that matches no source stays `unresolved` rather
than being assigned a tier, because a wrong "standard of care" label is the most
dangerous error this interface could make.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

V2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "application" / "packages" / "pipeline_core" / "src"))

from drug_map import normalize_drug_name  # noqa: E402
from v3_payload import copy_payloads_to_app, v3_interim  # noqa: E402

try:
    from pipeline_core.clinical_comparators import CLINICAL_COMPARATORS
    from pipeline_core.nominations import BREAST_CONTEXT_DRUGS
except Exception:  # noqa: BLE001
    BREAST_CONTEXT_DRUGS, CLINICAL_COMPARATORS = set(), {}

PRISM = REPO_ROOT / "depmap_data" / "primary-screen-replicate-collapsed-treatment-info.csv"
COMPOUND_INFO = REPO_ROOT / "compoundinfo_beta.txt"

TIER_LABELS = {
    "standard_of_care": "Breast standard of care",
    "investigational": "Under investigation",
    "not_human": "Not usable in humans",
    "unresolved": "Not classified",
}

PHASE_TO_TIER = {
    "launched": "investigational",  # approved, but not for breast — a repurposing hypothesis
    "phase 3": "investigational",
    "phase 2/phase 3": "investigational",
    "phase 2": "investigational",
    "phase 1/phase 2": "investigational",
    "phase 1": "investigational",
    "preclinical": "not_human",
    "withdrawn": "not_human",
}


def soc_names() -> set[str]:
    names = {normalize_drug_name(d) for d in BREAST_CONTEXT_DRUGS}
    names |= {normalize_drug_name(d) for d in CLINICAL_COMPARATORS}
    return {n for n in names if n}


def prism_table() -> dict[str, dict]:
    if not PRISM.is_file():
        print("WARN: PRISM treatment info absent; phase unavailable")
        return {}
    frame = pd.read_csv(PRISM, low_memory=False)
    out: dict[str, dict] = {}
    for _, row in frame.iterrows():
        key = normalize_drug_name(row.get("name"))
        if not key or key in out:
            continue
        phase = str(row.get("phase") or "").strip()
        out[key] = {
            "phase": phase or None,
            "indication": None if str(row.get("indication")) in ("nan", "NA", "") else str(row.get("indication")),
            "disease_area": None if str(row.get("disease.area")) in ("nan", "NA", "") else str(row.get("disease.area")),
        }
    return out


def compound_info() -> dict[str, dict]:
    if not COMPOUND_INFO.is_file():
        return {}
    frame = pd.read_csv(COMPOUND_INFO, sep="\t", low_memory=False)
    out: dict[str, dict] = {}
    for _, row in frame.iterrows():
        key = normalize_drug_name(row.get("cmap_name"))
        if not key or key in out:
            continue
        target = str(row.get("target") or "").strip()
        moa = str(row.get("moa") or "").strip()
        if target or moa:
            out[key] = {"target": target or None, "moa": moa or None}
    return out


def main() -> int:
    dest = v3_interim(V2_ROOT)
    evidence = json.loads((V2_ROOT / "data" / "reference" / "breast_evidence_sets.json").read_text())
    entries = evidence["entries"]
    default_tier = evidence["default_tier"]

    cohort_path = dest / "cohort_payload.json"
    cohort = json.loads(cohort_path.read_text())

    # --- features -------------------------------------------------------
    counts: dict[str, int] = {}
    for row in cohort.get("cluster_profiles") or []:
        hit = entries.get(str(row.get("feature")))
        tier = hit["tier"] if hit else default_tier
        row["evidence_tier"] = tier
        row["evidence_source"] = hit["source"] if hit else None
        counts[tier] = counts.get(tier, 0) + 1
    print(f"features tiered: {counts}")
    cohort["evidence_reference"] = {
        "schema": evidence["schema"],
        "curated_date": evidence["curated_date"],
        "tiers": evidence["tiers"],
        "caveat": evidence["caveat"],
    }

    # --- compounds ------------------------------------------------------
    soc = soc_names()
    prism = prism_table()
    info = compound_info()
    print(f"sources: {len(soc)} standard-of-care names · {len(prism)} PRISM phases · {len(info)} target/MOA rows")

    def classify(name: str) -> dict:
        key = normalize_drug_name(name)
        meta = info.get(key, {})
        row = prism.get(key, {})
        phase = (row.get("phase") or "").lower()
        if key in soc:
            tier, why = "standard_of_care", "On the curated breast standard-of-care list."
        elif phase in PHASE_TO_TIER:
            tier = PHASE_TO_TIER[phase]
            if phase == "launched":
                why = "Approved in humans, but not a breast standard of care — a repurposing hypothesis."
            elif tier == "not_human":
                why = f"PRISM development status: {row.get('phase')}. Not available for human use."
            else:
                why = f"PRISM development status: {row.get('phase')}."
        else:
            tier, why = "unresolved", "No development status found in the sources on hand."
        return {
            "evidence_tier": tier,
            "evidence_label": TIER_LABELS[tier],
            "evidence_reason": why,
            "max_phase": row.get("phase"),
            "approved_indication": row.get("indication"),
            "target": meta.get("target"),
            "moa": meta.get("moa"),
        }

    tier_counts: dict[str, int] = {}
    for block in list((cohort.get("reversal_by_cluster") or {}).values()):
        for member in block.get("members") or []:
            member.update(classify(member.get("canonical") or member.get("drug")))
            tier_counts[member["evidence_tier"]] = tier_counts.get(member["evidence_tier"], 0) + 1
    cohort["evidence_tier_labels"] = TIER_LABELS
    cohort_path.write_text(json.dumps(cohort, indent=2))

    patients = {}
    for path in sorted(dest.glob("payload_*.json")):
        payload = json.loads(path.read_text())
        block = payload.get("reversal_candidates")
        if block:
            for member in block.get("members") or []:
                member.update(classify(member.get("canonical") or member.get("drug")))

        # Tier the plotted curves too. A drug can be a breast standard of care
        # without having been retrieved (lapatinib is), and a retrieved drug can
        # be investigational (taselisib, vorinostat) — so "retrieved" is not a
        # synonym for any development status and must not be shown as one.
        retrieved = {
            str(m.get("canonical") or m.get("drug")).lower()
            for m in ((block or {}).get("members") or [])
        }
        for line in payload.get("nearest_lines") or []:
            for curve in line.get("curves") or []:
                name = str(curve.get("canonical") or curve.get("drug"))
                curve.update(classify(name))
                curve["retrieved"] = name.lower() in retrieved
        path.write_text(json.dumps(payload, indent=2))
        patients[payload["patient_id"]] = payload

    copy_payloads_to_app(cohort, patients, REPO_ROOT)
    print(f"compounds tiered per cluster: {tier_counts}")
    print("payloads copied to the app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
