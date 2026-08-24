"""Signature reversal against LINCS/GCTX with explicit provenance."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from drug_map import normalize_drug_name

ENDOCRINE = {"tamoxifen", "fulvestrant", "raloxifene"}
HER2_AGENTS = {"lapatinib", "neratinib", "tucatinib", "trastuzumab"}

SOURCE_GCTX = "lincs_gctx"
SOURCE_COMPACT = "compact_gctx"
SOURCE_PROXY = "committed_table_proxy"
SOURCE_SMOKE = "synthetic_smoke"


def connectivity_scores(signature: pd.Series, perturbations: pd.DataFrame) -> pd.Series:
    """Pearson correlation on overlapping genes; reversal is the negated score."""
    sig = signature.dropna()
    shared = [g for g in perturbations.columns if g in sig.index]
    if len(shared) < 5:
        return pd.Series(dtype=float)
    s = sig[shared].to_numpy(float)
    mat = perturbations[shared].to_numpy(float)
    s = s - np.nanmean(s)
    mat = mat - np.nanmean(mat, axis=1, keepdims=True)
    denom = np.linalg.norm(s) * np.linalg.norm(mat, axis=1)
    denom = np.where(denom == 0, np.nan, denom)
    corr = (mat @ s) / denom
    return pd.Series(-corr, index=perturbations.index, name="reversal")


def rank_reversal(
    signature: pd.Series,
    perturbations: pd.DataFrame,
    meta: pd.DataFrame | None = None,
    source: str = SOURCE_SMOKE,
    top_n: int = 50,
) -> pd.DataFrame:
    scores = connectivity_scores(signature, perturbations)
    if scores.empty:
        return pd.DataFrame(columns=["drug", "canonical", "reversal_score", "rank", "source", "validated"])
    df = scores.sort_values(ascending=False).reset_index()
    df.columns = ["drug", "reversal_score"]
    if meta is not None and "drug" in meta.columns:
        df = df.merge(meta, on="drug", how="left")
    df["canonical"] = df["drug"].map(normalize_drug_name)
    df["rank"] = np.arange(1, len(df) + 1)
    df["source"] = source
    df["validated"] = False
    df["threshold_rule"] = "connectivity_reversal_top_n"
    return df.head(top_n)


def load_perturbations(paths: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Prefer full GCTX compact parquet; else committed table; else empty (caller synthesises)."""
    compact = paths.get("compact_matrix")
    meta_path = paths.get("compact_meta")
    if compact and Path(compact).is_file():
        mat = pd.read_parquet(compact)
        meta = pd.read_parquet(meta_path) if meta_path and Path(meta_path).is_file() else pd.DataFrame()
        return mat, meta, SOURCE_COMPACT
    table = paths.get("committed_table")
    if table and Path(table).is_file() and Path(table).suffix.lower() in {".parquet", ".gctx"}:
        df = pd.read_parquet(table) if Path(table).suffix.lower() == ".parquet" else pd.DataFrame()
        return df, pd.DataFrame(), SOURCE_PROXY
    return pd.DataFrame(), pd.DataFrame(), SOURCE_SMOKE


def known_drug_positive_control(top_hits: pd.DataFrame, cluster_role: str) -> dict:
    names = set(top_hits["canonical"].map(str).str.lower()) if not top_hits.empty else set()
    if cluster_role == "er_high":
        hits = ENDOCRINE & names
        return {"passed": len(hits) >= 1, "hits": sorted(hits), "role": cluster_role}
    if cluster_role == "her2_amplified":
        hits = HER2_AGENTS & names
        return {"passed": len(hits) >= 1, "hits": sorted(hits), "role": cluster_role}
    return {"passed": True, "hits": [], "role": cluster_role, "note": "no positive-control set for this cluster"}
