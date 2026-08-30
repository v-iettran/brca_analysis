"""Methylation-silencing reliability for TF regulons — distinct from completeness."""

from __future__ import annotations

import numpy as np
import pandas as pd

SILENCING_THRESHOLD = 0.6


def completeness_flag(tf_activity: pd.DataFrame) -> pd.Series:
    """Share of samples with a finite score. This is NOT methylation reliability."""
    return tf_activity.notna().mean(axis=0)


def methylation_silencing_reliability(
    tf_to_genes: dict[str, list[str]],
    methylation: pd.DataFrame | None,
    expression: pd.DataFrame | None = None,
    threshold: float = SILENCING_THRESHOLD,
) -> pd.DataFrame:
    """Flag TFs whose regulon is promoter-hypermethylated (optionally with low RNA).

    If methylation is absent the source is ``unavailable`` — never relabelled
    as a methylation result.
    """
    rows = []
    if methylation is None or methylation.empty:
        for tf, genes in tf_to_genes.items():
            rows.append({
                "tf": tf,
                "reliability": "unavailable",
                "reliability_reason": "No methylation matrix; silencing not assessed.",
                "source": "unavailable",
                "silenced_fraction": None,
                "n_regulon": len(genes),
            })
        return pd.DataFrame(rows)
    meth = methylation.copy()
    meth.columns = meth.columns.astype(str)
    for tf, genes in tf_to_genes.items():
        present = [g for g in genes if g in meth.columns]
        if not present:
            rows.append({
                "tf": tf,
                "reliability": "unknown",
                "reliability_reason": "Regulon genes absent from methylation matrix.",
                "source": "methylation",
                "silenced_fraction": None,
                "n_regulon": len(genes),
            })
            continue
        silenced = (meth[present] >= threshold).mean().mean()
        low_rna = False
        if expression is not None:
            overlap = [g for g in present if g in expression.columns]
            if overlap:
                low_rna = float(expression[overlap].mean().mean()) < float(np.nanmedian(expression.to_numpy(float)))
        flagged = bool(silenced >= 0.5 and (expression is None or low_rna))
        rows.append({
            "tf": tf,
            "reliability": "low" if flagged else "high",
            "reliability_reason": (
                "Regulon promoters are methylation-silenced."
                if flagged
                else "No evidence of regulon methylation silencing."
            ),
            "source": "methylation",
            "silenced_fraction": float(silenced),
            "n_regulon": len(present),
        })
    return pd.DataFrame(rows)
