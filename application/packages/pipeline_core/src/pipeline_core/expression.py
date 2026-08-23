"""Loading and aligning METABRIC expression data.

METABRIC is used as the reference RNA population: it is the cohort the MOFA
cluster signatures were derived from, so it is also the correct background
distribution to z-score a new single patient against (see
``reference_gene_stats``). The raw 689 MB expression matrix is cached once to
parquet under ``ARTIFACT_DIR`` so repeated API calls do not re-parse it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

import numpy as np
import pandas as pd

from pipeline_core.config import ARTIFACT_DIR, METABRIC_DIR

_EXPRESSION_CACHE = ARTIFACT_DIR / "metabric_expression_cache.parquet"
_REFERENCE_STATS_CACHE = ARTIFACT_DIR / "metabric_gene_reference_stats.parquet"


def load_metabric_expression(force_reload: bool = False) -> pd.DataFrame:
    """Return METABRIC expression as a genes (rows) x samples (cols) DataFrame.

    Duplicate Hugo symbols are collapsed by mean, matching the convention used
    by ``final-project/brca_target_pipeline.py``.
    """
    if _EXPRESSION_CACHE.exists() and not force_reload:
        return pd.read_parquet(_EXPRESSION_CACHE)

    path = METABRIC_DIR / "data_mrna_illumina_microarray.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"METABRIC expression file not found at {path}. Set METABRIC_DIR."
        )
    raw = pd.read_csv(path, sep="\t", comment="#")
    raw = raw.drop(columns=["Entrez_Gene_Id"], errors="ignore")
    raw = raw.dropna(subset=["Hugo_Symbol"])
    raw["Hugo_Symbol"] = raw["Hugo_Symbol"].str.strip().str.upper()
    expr = raw.groupby("Hugo_Symbol").mean(numeric_only=True)
    expr.index.name = "gene"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    expr.to_parquet(_EXPRESSION_CACHE)
    return expr


@lru_cache(maxsize=1)
def load_mofa_cluster_labels() -> pd.Series:
    """Return a Series mapping METABRIC PATIENT_ID -> MOFA_CLUSTER (int)."""
    from pipeline_core.config import MOFA_CLUSTERS_DIR

    path = MOFA_CLUSTERS_DIR / "mofa_clusters.csv"
    if not path.exists():
        raise FileNotFoundError(f"MOFA cluster labels not found at {path}")
    df = pd.read_csv(path, index_col=0)
    return df["MOFA_CLUSTER"].astype(int)


def reference_gene_stats(force_reload: bool = False) -> pd.DataFrame:
    """Per-gene mean/sd across the METABRIC reference population.

    Used to z-score a *single* incoming patient's expression the same way the
    Q5 pipeline z-scores an entire GEO cohort (``row_zscore_matrix`` in
    ``scripts/Q5.R``), but with a persisted reference population instead of an
    n=1 cohort (which would be degenerate).
    """
    if _REFERENCE_STATS_CACHE.exists() and not force_reload:
        return pd.read_parquet(_REFERENCE_STATS_CACHE)

    expr = load_metabric_expression()
    stats = pd.DataFrame(
        {"mean": expr.mean(axis=1, skipna=True), "sd": expr.std(axis=1, skipna=True)}
    )
    stats.loc[stats["sd"] == 0, "sd"] = np.nan
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stats.to_parquet(_REFERENCE_STATS_CACHE)
    return stats


@dataclass
class AlignedExpression:
    """A patient's expression vector aligned to a reference gene universe."""

    values: pd.Series  # raw (non-standardized) values, indexed by gene
    z_scores: pd.Series  # z-scored against the METABRIC reference population
    coverage_fraction: float
    genes_found: int
    genes_requested: int
    missing_genes: list[str]


def align_patient_expression(
    patient_expression: Mapping[str, float],
    reference_genes: pd.Index | None = None,
) -> AlignedExpression:
    """Align an arbitrary patient gene->value mapping onto the reference gene set.

    Gene symbols are upper-cased/trimmed to be robust to minor formatting
    differences in uploaded RNA-seq data.
    """
    ref_stats = reference_gene_stats()
    reference_index = (
        reference_genes if reference_genes is not None else ref_stats.index
    )

    cleaned = {
        str(gene).strip().upper(): float(value)
        for gene, value in patient_expression.items()
        if value is not None and np.isfinite(float(value))
    }
    found_genes = [g for g in reference_index if g in cleaned]
    missing_genes = [g for g in reference_index if g not in cleaned]
    values = pd.Series({g: cleaned[g] for g in found_genes}, dtype=float)

    aligned_stats = ref_stats.loc[values.index]
    z = (values - aligned_stats["mean"]) / aligned_stats["sd"]
    z = z.replace([np.inf, -np.inf], np.nan).dropna()

    coverage = len(found_genes) / max(len(reference_index), 1)

    return AlignedExpression(
        values=values,
        z_scores=z,
        coverage_fraction=coverage,
        genes_found=len(found_genes),
        genes_requested=len(reference_index),
        missing_genes=missing_genes[:50],
    )
