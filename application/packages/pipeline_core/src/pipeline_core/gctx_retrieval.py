"""Configurable GCTX / L1000 reversal scoring for List 1 and List 2.

Runtime never opens the 33 GB GCTX file. Prefer the compact breast-cell-line
artifact produced by ``jobs/build_compact_gctx_artifact.py``. When that
artifact is absent, List 1 uses committed cluster drug tables and List 2 uses
a deterministic residual-aware proxy over those same tables so the demo and
tests remain offline-capable.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from pipeline_core.config import (
    COMPACT_GCTX_MATRIX,
    COMPACT_GCTX_META,
    DEFAULT_TOP_DOWN,
    DEFAULT_TOP_UP,
    MOFA_CLUSTERS_DIR,
    N_MOFA_CLUSTERS,
)
from pipeline_core.drug_names import normalize_drug_name
from pipeline_core.gctx_evidence import blended_drug_evidence, load_all_cluster_drug_tables
from pipeline_core.residual_signatures import (
    ClusterSignatureArms,
    ResidualSignature,
    clamp_signature_size,
    cluster_signature_arms,
    patient_residual_signature,
)


@dataclass
class DrugReversalHit:
    drug: str
    canonical: str
    reversal_score: float
    percentile: float
    rank: int
    n_signatures: int | None
    n_cell_lines: int | None
    targets: list[str]
    source: str
    consistency: float | None = None


def compact_gctx_available() -> bool:
    return COMPACT_GCTX_MATRIX.exists() and COMPACT_GCTX_META.exists()


@lru_cache(maxsize=1)
def _compact_gene_columns() -> frozenset[str]:
    """Return available gene columns without loading the 5.9 GB matrix."""
    import pyarrow.parquet as pq

    schema_names = pq.ParquetFile(COMPACT_GCTX_MATRIX).schema.names
    return frozenset(str(name).upper() for name in schema_names if not str(name).startswith("__index"))


@lru_cache(maxsize=1)
def _load_compact_meta() -> pd.DataFrame:
    meta = pd.read_parquet(COMPACT_GCTX_META)
    if "sig_id" in meta.columns:
        meta = meta.set_index("sig_id", drop=True)
    meta.index = meta.index.astype(str)
    return meta


def score_gene_set_against_compact(
    up_genes: list[str], down_genes: list[str]
) -> pd.DataFrame:
    """Score every compact signature: mean(up) - mean(down); higher reversal = -score."""
    available = _compact_gene_columns()
    up = [g.upper() for g in up_genes if g.upper() in available]
    down = [g.upper() for g in down_genes if g.upper() in available]
    if len(up) < 5 or len(down) < 5:
        return pd.DataFrame(
            columns=[
                "drug",
                "canonical",
                "reversal_score",
                "percentile",
                "rank",
                "n_signatures",
                "n_cell_lines",
                "targets",
                "source",
                "consistency",
            ]
        )

    # Parquet is columnar: load only the selected signature genes rather than
    # materializing the full multi-GB breast-cell-line matrix.
    selected = list(dict.fromkeys([*up, *down]))
    matrix = pd.read_parquet(COMPACT_GCTX_MATRIX, columns=selected)
    matrix.columns = [str(c).upper() for c in matrix.columns]
    matrix.index = matrix.index.astype(str)
    meta = _load_compact_meta()

    raw = matrix[up].mean(axis=1) - matrix[down].mean(axis=1)
    scored = meta.copy()
    scored["raw_score"] = raw.reindex(scored.index).to_numpy()
    scored["reversal_score"] = -scored["raw_score"]
    scored["canonical"] = scored["drug"].map(normalize_drug_name)

    agg = (
        scored.dropna(subset=["reversal_score"])
        .groupby("canonical", as_index=False)
        .agg(
            drug=("drug", "first"),
            reversal_score=("reversal_score", "max"),
            median_score=("reversal_score", "median"),
            n_signatures=("reversal_score", "count"),
            n_cell_lines=("cell_id", "nunique") if "cell_id" in scored.columns else ("drug", "count"),
            consistency=("reversal_score", lambda s: float((s > 0).mean()) if len(s) else None),
        )
    )
    if "targets" in scored.columns:
        targets = (
            scored.dropna(subset=["targets"])
            .groupby("canonical")["targets"]
            .apply(lambda s: sorted({t for item in s for t in str(item).split(";") if t}))
        )
        agg["targets"] = agg["canonical"].map(lambda c: targets.get(c, []))
    else:
        agg["targets"] = [[] for _ in range(len(agg))]

    agg = agg.sort_values("reversal_score", ascending=False).reset_index(drop=True)
    n = len(agg)
    agg["rank"] = np.arange(1, n + 1)
    agg["percentile"] = 1.0 - (agg["rank"] - 1) / max(n - 1, 1)
    agg["source"] = "compact_gctx"
    return agg


def _proxy_list2_from_cluster_tables(
    residual: ResidualSignature,
    cluster_probabilities: dict[int, float],
    top_n: int | None = 50,
) -> pd.DataFrame:
    """Offline-capable List 2 proxy when the compact GCTX artifact is missing.

    Transfers the closest-cluster List 1 ranking, reweighted by residual gene-set
    overlap with the cluster signature and by residual magnitude on drug targets.
    """
    tables = load_all_cluster_drug_tables()
    cluster_id = residual.cluster_id
    table = tables.get(cluster_id)
    if table is None or table.empty:
        return pd.DataFrame()

    cluster_arms = cluster_signature_arms(cluster_id, residual.top_up, residual.top_down)
    cluster_up = set(cluster_arms.up.genes)
    cluster_down = set(cluster_arms.down.genes)
    resid_up = set(residual.up.genes)
    resid_down = set(residual.down.genes)

    def jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / max(len(a | b), 1)

    overlap = 0.5 * (jaccard(resid_up, cluster_up) + jaccard(resid_down, cluster_down))
    residual_weights = {**residual.up.values, **residual.down.values}

    rows = []
    for drug_lower, row in table.iterrows():
        targets = (
            [t.strip().upper() for t in str(row.get("targets", "")).split(";") if t.strip()]
            if pd.notna(row.get("targets"))
            else []
        )
        target_hit = sum(abs(residual_weights.get(t, 0.0)) for t in targets)
        base = float(row["percentile"])
        # Residual personalization: keep cluster prior, boost drugs whose targets
        # sit in the residual arms and when residual resembles the cluster signature.
        score = 0.55 * base + 0.25 * overlap * base + 0.20 * np.tanh(target_hit)
        rows.append(
            {
                "drug": row["drug"] if "drug" in row else drug_lower,
                "canonical": normalize_drug_name(row["drug"] if "drug" in row else drug_lower),
                "reversal_score": score,
                "n_signatures": int(row["n_signatures"]) if pd.notna(row.get("n_signatures")) else None,
                "n_cell_lines": None,
                "targets": targets,
                "source": "residual_proxy",
                "consistency": overlap,
            }
        )

    # Also blend soft probabilities into a secondary prior for mixed patients.
    if len(cluster_probabilities) > 1:
        blended = []
        all_drugs = set()
        for tbl in tables.values():
            all_drugs.update(tbl["drug"].tolist())
        for drug in all_drugs:
            evidence = blended_drug_evidence(cluster_probabilities, drug)
            if evidence["blended_percentile"] is None:
                continue
            blended.append((normalize_drug_name(drug), evidence["blended_percentile"], drug))
        blend_map = {c: (p, d) for c, p, d in blended}
        for row in rows:
            if row["canonical"] in blend_map:
                p, d = blend_map[row["canonical"]]
                row["reversal_score"] = 0.7 * row["reversal_score"] + 0.3 * p
                row["drug"] = d

    result = pd.DataFrame(rows).sort_values("reversal_score", ascending=False).reset_index(drop=True)
    n = len(result)
    result["rank"] = np.arange(1, n + 1)
    result["percentile"] = 1.0 - (result["rank"] - 1) / max(n - 1, 1)
    return result if top_n is None else result.head(top_n)


def list1_cluster_reversal(
    cluster_id: int,
    cluster_probabilities: dict[int, float] | None = None,
    top_up: int | None = None,
    top_down: int | None = None,
    top_n: int | None = 100,
) -> tuple[ClusterSignatureArms, pd.DataFrame]:
    """List 1: compounds reversing the closest-cluster one-vs-rest signature."""
    top_up = clamp_signature_size(top_up, DEFAULT_TOP_UP)
    top_down = clamp_signature_size(top_down, DEFAULT_TOP_DOWN)
    arms = cluster_signature_arms(cluster_id, top_up, top_down)

    if compact_gctx_available():
        hits = score_gene_set_against_compact(arms.up.genes, arms.down.genes)
        if top_n is not None:
            hits = hits.head(top_n)
        return arms, hits

    # Fall back to committed per-cluster GCTX tables (built at top_up/down=150).
    tables = load_all_cluster_drug_tables()
    table = tables[int(cluster_id)].reset_index()
    rows = []
    for _, row in table.iterrows():
        rows.append(
            {
                "drug": row["drug"],
                "canonical": normalize_drug_name(row["drug"]),
                "reversal_score": float(row["reversal_score"]),
                "percentile": float(row["percentile"]),
                "rank": int(row["drug_rank"]),
                "n_signatures": int(row["n_signatures"]) if pd.notna(row.get("n_signatures")) else None,
                "n_cell_lines": None,
                "targets": (
                    [t for t in str(row.get("targets", "")).split(";") if t]
                    if pd.notna(row.get("targets"))
                    else []
                ),
                "source": "cluster_drug_table",
                "consistency": None,
            }
        )
    hits = pd.DataFrame(rows).sort_values("rank")
    if top_n is not None:
        hits = hits.head(top_n)
    hits = hits.reset_index(drop=True)

    # Soft-blend note for mixed patients: keep closest-cluster List 1 primary,
    # but annotate blended percentile when probabilities are provided.
    if cluster_probabilities:
        hits["blended_percentile"] = [
            blended_drug_evidence(cluster_probabilities, d)["blended_percentile"] for d in hits["drug"]
        ]
    return arms, hits


def list2_patient_residual_reversal(
    patient_expression: dict[str, float],
    cluster_id: int,
    cluster_probabilities: dict[int, float] | None = None,
    top_up: int | None = None,
    top_down: int | None = None,
    top_n: int | None = 100,
) -> tuple[ResidualSignature, pd.DataFrame]:
    """List 2: compounds reversing the patient residual vs cluster centroid."""
    residual = patient_residual_signature(
        patient_expression, cluster_id, top_up=top_up, top_down=top_down
    )
    if compact_gctx_available() and residual.up.genes and residual.down.genes:
        hits = score_gene_set_against_compact(residual.up.genes, residual.down.genes)
        if top_n is not None:
            hits = hits.head(top_n)
        return residual, hits

    hits = _proxy_list2_from_cluster_tables(
        residual, cluster_probabilities or {cluster_id: 1.0}, top_n=top_n
    )
    return residual, hits
