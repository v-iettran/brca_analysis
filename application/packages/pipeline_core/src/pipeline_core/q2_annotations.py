"""Q2 annotation helpers used only as evidence columns on nominations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline_core.drug_names import normalize_drug_name
from pipeline_core.q2_evidence import score_patient_all_drugs


def q2_annotations_for_drugs(
    patient_expression: dict[str, float], drugs: list[str]
) -> dict[str, dict]:
    table = score_patient_all_drugs(patient_expression)
    # Build percentile within scored Q2 drugs for this patient.
    scored = table.dropna(subset=["raw_score"]).copy()
    if not scored.empty:
        ranks = scored["raw_score"].rank(method="average", ascending=True)
        scored["sensitivity_percentile"] = (ranks - 0.5) / len(scored)
    else:
        scored["sensitivity_percentile"] = np.nan

    by_canonical = {}
    for drug, row in scored.iterrows():
        by_canonical[normalize_drug_name(drug)] = {
            "drug": drug,
            "raw_score": _safe(row.get("raw_score")),
            "z_score": _safe(row.get("z_score")),
            "sensitivity_percentile": _safe(row.get("sensitivity_percentile")),
            "genes_used": int(row.get("genes_used") or 0),
            "evidence_category": row.get("evidence_category"),
            "model_support": _safe(row.get("model_support")),
            "model_spearman": _safe(row.get("model_spearman")),
            "external_spearman": _safe(row.get("external_spearman")),
            "interpretation": (
                "Q2 cell-line sensitivity annotation only. Not a clinical dose "
                "and not used to nominate the drug."
            ),
        }

    # Also keep unmatched requested drugs as unavailable annotations.
    out = {}
    for drug in drugs:
        key = normalize_drug_name(drug)
        out[key] = by_canonical.get(
            key,
            {
                "drug": drug,
                "raw_score": None,
                "z_score": None,
                "sensitivity_percentile": None,
                "genes_used": 0,
                "evidence_category": None,
                "model_support": None,
                "model_spearman": None,
                "external_spearman": None,
                "interpretation": "Q2 evidence unavailable for this compound.",
            },
        )
    return out


def _safe(value) -> float | None:
    try:
        f = float(value)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None
