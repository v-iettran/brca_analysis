"""Scan Q4 and overlap-facing compound names for unresolved registry rows."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline_core.compound_registry import is_anonymous_perturbagen, lookup_compound
from pipeline_core.config import COMPOUND_REVIEW_QUEUE_DIR, MOFA_CLUSTERS_DIR, SYNTHETIC_PATIENTS_DIR
from pipeline_core.drug_names import normalize_drug_name


def _cluster_names() -> Counter:
    counts: Counter = Counter()
    for path in sorted(MOFA_CLUSTERS_DIR.glob("cluster_*_drug_targets.csv")):
        frame = pd.read_csv(path, usecols=["drug", "drug_rank"])
        for _, row in frame.iterrows():
            if int(row["drug_rank"]) > 500:
                continue
            counts[normalize_drug_name(row["drug"])] += 1
    return counts


def _synthetic_names() -> set[str]:
    names: set[str] = set()
    index_path = SYNTHETIC_PATIENTS_DIR / "index.json"
    if not index_path.exists():
        return names
    for item in json.loads(index_path.read_text()):
        for drug in item.get("administered_regimen") or []:
            names.add(normalize_drug_name(drug))
    return names


def scan_unresolved() -> pd.DataFrame:
    cluster_counts = _cluster_names()
    synthetic = _synthetic_names()
    rows = []
    for canonical, frequency in cluster_counts.most_common():
        if lookup_compound(name=canonical) is not None and not is_anonymous_perturbagen(canonical):
            continue
        rows.append(
            {
                "canonical": canonical,
                "q4_top500_frequency": int(frequency),
                "in_synthetic_regimen": canonical in synthetic,
                "anonymous_lincs_id": is_anonymous_perturbagen(canonical),
                "status": "unresolved",
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(
            ["in_synthetic_regimen", "q4_top500_frequency"],
            ascending=[False, False],
        ).reset_index(drop=True)
        frame["priority_rank"] = range(1, len(frame) + 1)
    COMPOUND_REVIEW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    out = COMPOUND_REVIEW_QUEUE_DIR / "unresolved_candidates.parquet"
    if frame.empty:
        frame = pd.DataFrame(
            columns=[
                "canonical",
                "q4_top500_frequency",
                "in_synthetic_regimen",
                "anonymous_lincs_id",
                "status",
                "scanned_at",
                "priority_rank",
            ]
        )
    frame.to_parquet(out, index=False)
    frame.to_csv(COMPOUND_REVIEW_QUEUE_DIR / "unresolved_candidates.csv", index=False)
    return frame


def main() -> None:
    frame = scan_unresolved()
    print(f"Wrote {len(frame)} unresolved candidates to {COMPOUND_REVIEW_QUEUE_DIR}")


if __name__ == "__main__":
    main()
