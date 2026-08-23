"""Q5 cell-line-aligned ALMANAC combination evidence for overlap nominations.

Loads committed tables from ``scripts/Q5.R`` / ``predictor_model.R`` outputs.
Combinations are preclinical priority evidence only -- never dosage or pCR.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from pipeline_core.config import Q5_ALMANAC_DIR
from pipeline_core.drug_names import normalize_drug_name


@lru_cache(maxsize=1)
def load_eligible_almanac_pairs() -> pd.DataFrame:
    path = Q5_ALMANAC_DIR / "q2_almanac_eligible_aligned_pairs.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["drug_a_canonical"] = df["drug_a"].map(normalize_drug_name)
    df["drug_b_canonical"] = df["drug_b"].map(normalize_drug_name)
    return df


def combinations_for_overlap(
    overlap_canonicals: list[str],
    q2_percentiles: dict[str, float] | None = None,
    top_n: int = 10,
) -> list[dict]:
    """Return ALMANAC pairs where both drugs are in the overlap nomination set."""
    pairs = load_eligible_almanac_pairs()
    if pairs.empty or not overlap_canonicals:
        return []

    allowed = {normalize_drug_name(d) for d in overlap_canonicals}
    q2_percentiles = q2_percentiles or {}
    matched = pairs[
        pairs["drug_a_canonical"].isin(allowed) & pairs["drug_b_canonical"].isin(allowed)
    ].copy()
    if matched.empty:
        return []

    rows = []
    for _, row in matched.iterrows():
        a = row["drug_a_canonical"]
        b = row["drug_b_canonical"]
        pa = float(q2_percentiles.get(a, 0.0) or 0.0)
        pb = float(q2_percentiles.get(b, 0.0) or 0.0)
        component = (max(pa, 0.0) * max(pb, 0.0)) ** 0.5
        aligned = float(row.get("aligned_pair_support", 0.0) or 0.0)
        # Transparent weighted priority without legacy Q4 term.
        priority = 0.60 * component + 0.40 * aligned
        rows.append(
            {
                "drug_a": row["drug_a"],
                "drug_b": row["drug_b"],
                "combination": row.get("combination", f"{row['drug_a']} + {row['drug_b']}"),
                "aligned_cell_lines": int(row.get("aligned_cell_lines", 0) or 0),
                "aligned_cell_line_names": row.get("aligned_cell_line_names"),
                "aligned_median_almanac_combo_score": _safe(row.get("aligned_median_almanac_combo_score")),
                "aligned_pair_support": aligned,
                "component_support": component,
                "q2_percentile_a": pa if a in q2_percentiles else None,
                "q2_percentile_b": pb if b in q2_percentiles else None,
                "combination_priority": priority,
                "cell_line_alignment_confidence": row.get("cell_line_alignment_confidence"),
                "interpretation": (
                    "Preclinical Q2–ALMANAC cell-line-aligned combination priority. "
                    "Not a calibrated clinical response probability and not a dose recommendation."
                ),
            }
        )

    rows.sort(key=lambda r: r["combination_priority"], reverse=True)
    for i, row in enumerate(rows[:top_n], start=1):
        row["rank"] = i
    return rows[:top_n]


def _safe(value) -> float | None:
    try:
        f = float(value)
        return f if f == f else None
    except (TypeError, ValueError):
        return None
