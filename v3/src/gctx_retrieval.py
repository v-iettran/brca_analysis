"""Signature reversal against LINCS/GCTX with explicit provenance."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

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


# --------------------------------------------------------------------------
# LINCS 2020 beta compact artifact (breast trt_cp)
#
# The 33 GB raw `level5_beta_trt_cp_*.gctx` is a one-time input, not a runtime
# dependency: `build_compact_gctx_artifact.py` reduces it to a breast-line
# matrix plus its signature metadata. This loader consumes that artifact.
#
# The matrix is indexed by `sig_id`, not by compound: one drug appears many
# times across doses, timepoints and cell lines. Scoring therefore happens per
# signature and is aggregated per compound afterwards — collapsing first would
# average away the dose-response structure that makes a hit credible.

SOURCE_BREAST_COMPACT = "lincs_breast_trt_cp"

MATRIX_FILE = "breast_trt_cp_matrix.parquet"
SIGNATURE_FILE = "breast_trt_cp_signatures.parquet"


def query_signature(signature: pd.Series, n_side: int = 150) -> pd.Series:
    """Top `n_side` up- and down-regulated genes.

    Connectivity is defined against a query signature of the most-changed
    genes, not the whole transcriptome: the tail is mostly noise and including
    it both dilutes the correlation and forces a far larger matrix read.
    """
    sig = signature.dropna().astype(float)
    if sig.empty:
        return sig
    ordered = sig.sort_values()
    down = ordered.head(n_side)
    up = ordered.tail(n_side)
    return pd.concat([down, up])


def load_breast_compact(
    directory: Path, genes: list[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load the compact breast perturbation matrix and its signature metadata.

    `genes` restricts the column read. The full matrix is ~92.8k x 12k float32
    (about 4.5 GB in memory); a query signature needs only a few hundred
    columns, so the subset read is what keeps this usable.
    """
    base = Path(directory)
    matrix_path = base / MATRIX_FILE
    meta_path = base / SIGNATURE_FILE
    if not matrix_path.is_file() or not meta_path.is_file():
        return pd.DataFrame(), pd.DataFrame(), SOURCE_SMOKE

    meta = pd.read_parquet(meta_path)
    if genes:
        available = set(pq.ParquetFile(matrix_path).schema_arrow.names)
        cols = [g for g in dict.fromkeys(genes) if g in available]
        if not cols:
            return pd.DataFrame(), meta, SOURCE_SMOKE
        mat = pd.read_parquet(matrix_path, columns=cols)
    else:
        mat = pd.read_parquet(matrix_path)
    return mat, meta, SOURCE_BREAST_COMPACT


def rank_reversal_by_signature(
    signature: pd.Series,
    perturbations: pd.DataFrame,
    meta: pd.DataFrame,
    source: str = SOURCE_BREAST_COMPACT,
    top_n: int = 50,
    min_signatures: int = 2,
    exemplar_only: bool = True,
) -> pd.DataFrame:
    """Score every signature, then aggregate per compound.

    A compound is summarised by the median reversal across its signatures.
    Median rather than max because the maximum over ~dozens of doses and
    timepoints is an order statistic that rewards noise, and a compound that
    only reverses in one arbitrary condition is not evidence of anything.
    """
    if perturbations.empty or meta.empty:
        return pd.DataFrame(
            columns=["drug", "canonical", "reversal_score", "rank", "source", "validated", "n_signatures"]
        )

    frame = meta
    if exemplar_only and "is_exemplar_sig" in frame.columns:
        keep = frame["is_exemplar_sig"].fillna(0).astype(float) > 0
        if keep.sum() >= 100:
            frame = frame[keep]
    if "qc_pass" in frame.columns:
        ok = frame["qc_pass"].fillna(1).astype(float) > 0
        if ok.sum() >= 100:
            frame = frame[ok]

    usable = perturbations.reindex(frame["sig_id"].astype(str)).dropna(how="all")
    if usable.empty:
        return pd.DataFrame(
            columns=["drug", "canonical", "reversal_score", "rank", "source", "validated", "n_signatures"]
        )

    scores = connectivity_scores(signature, usable)
    if scores.empty:
        return pd.DataFrame(
            columns=["drug", "canonical", "reversal_score", "rank", "source", "validated", "n_signatures"]
        )

    named = frame.set_index(frame["sig_id"].astype(str))["drug"].reindex(scores.index)
    df = pd.DataFrame({"drug": named.astype(str), "reversal_score": scores.to_numpy(float)})
    df = df[df["drug"].notna() & (df["drug"].str.lower() != "nan")]
    grouped = (
        df.groupby("drug")["reversal_score"]
        .agg(reversal_score="median", n_signatures="size")
        .reset_index()
    )
    grouped = grouped[grouped["n_signatures"] >= min_signatures]
    grouped = grouped.sort_values("reversal_score", ascending=False).reset_index(drop=True)
    grouped["canonical"] = grouped["drug"].map(normalize_drug_name)
    grouped["rank"] = np.arange(1, len(grouped) + 1)
    grouped["source"] = source
    grouped["validated"] = False
    grouped["threshold_rule"] = "connectivity_reversal_top_n"
    return grouped.head(top_n)
