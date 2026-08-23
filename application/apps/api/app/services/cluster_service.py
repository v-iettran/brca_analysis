"""Clinician-facing MOFA cluster signature details.

The committed signatures are PAM50-adjusted one-vs-rest expression
coefficients. Positive values mean higher expression in that cluster than in
the other METABRIC samples after adjustment; negative values mean lower
expression. They are descriptive associations, not causal effects or the
elastic-net classifier's own weights.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from pipeline_core.config import MOFA_CLUSTERS_DIR, N_MOFA_CLUSTERS


@lru_cache(maxsize=1)
def _load_signature_summary() -> pd.DataFrame:
    path = MOFA_CLUSTERS_DIR / "cluster_signature_summary.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing MOFA cluster signature summary: {path}")
    return pd.read_csv(path).set_index("cluster")


@lru_cache(maxsize=N_MOFA_CLUSTERS)
def _load_cluster_signature(cluster_id: int) -> pd.DataFrame:
    if not 0 <= cluster_id < N_MOFA_CLUSTERS:
        raise ValueError(f"cluster_id must be between 0 and {N_MOFA_CLUSTERS - 1}")
    path = MOFA_CLUSTERS_DIR / f"cluster_{cluster_id}_signature.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing MOFA cluster signature: {path}")
    signature = pd.read_csv(path)
    signature["gene"] = signature["gene"].astype(str).str.upper()
    return signature


def _serialize_gene(row: pd.Series, direction: str) -> dict:
    return {
        "gene": row["gene"],
        "coefficient": float(row["coef"]),
        "p_value": float(row["pval"]),
        "fdr": float(row["fdr"]),
        "direction": direction,
    }


def cluster_detail(cluster_id: int, patient_probability: float, top_n: int = 12) -> dict:
    top_n = min(max(top_n, 5), 50)
    signature = _load_cluster_signature(cluster_id)
    summary = _load_signature_summary().loc[cluster_id]

    positive = signature[signature["coef"] > 0].nlargest(top_n, "coef")
    negative = signature[signature["coef"] < 0].nsmallest(top_n, "coef")
    significant = int((signature["fdr"] < 0.10).sum())

    return {
        "cluster_id": cluster_id,
        "patient_probability": patient_probability,
        "n_in_cluster": int(summary["n_in"]),
        "n_out_cluster": int(summary["n_out"]),
        "genes_tested": int(summary["genes_tested"]),
        "significant_gene_count": significant,
        "coefficient_interpretation": (
            "PAM50-adjusted one-vs-rest expression difference. Positive coefficients "
            "indicate higher expression in this cluster; negative coefficients indicate "
            "lower expression. These are associations, not causal effects or treatment signals."
        ),
        "positive_genes": [_serialize_gene(row, "higher") for _, row in positive.iterrows()],
        "negative_genes": [_serialize_gene(row, "lower") for _, row in negative.iterrows()],
    }


def cluster_contains_gene(cluster_id: int, gene: str) -> bool:
    genes = set(_load_cluster_signature(cluster_id)["gene"])
    return gene.strip().upper() in genes
