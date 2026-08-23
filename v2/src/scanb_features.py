"""SCAN-B expression → PROGENy / CollecTRI, cached. Used by NB13 (no ODE)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TARGET_TO_PROGENY = {
    "ESR1": "Estrogen",
    "EGFR": "EGFR",
    "ERBB2": "EGFR",
    "IGF1R": "PI3K",
    "PIK3CA": "PI3K",
    "AKT1": "PI3K",
    "MTOR": "PI3K",
    "PTEN": "PI3K",
    "KRAS": "MAPK",
    "BRAF": "MAPK",
    "MAP2K1": "MAPK",
    "MAPK1": "MAPK",
    "CCND1": "p53",
    "CDK4": "p53",
    "CDK6": "p53",
    "CDKN2A": "p53",
    "RB1": "p53",
    "E2F1": "p53",
    "MKI67": "p53",
    "CDKN1A": "p53",
}


def scanb_expression_path(raw_scanb: Path) -> Path | None:
    hits = sorted(Path(raw_scanb).glob("GSE96058_gene_expression*.csv.gz"))
    return hits[0] if hits else None


def load_scanb_expression_subset(path: Path, keep_genes: set[str], n_samples: int | None = None) -> pd.DataFrame:
    """File is genes × samples (columns F1..). Returns samples × genes."""
    usecols = None
    header = pd.read_csv(path, nrows=0)
    cols = list(header.columns)
    sample_cols = cols[1:]
    if n_samples is not None:
        sample_cols = sample_cols[: int(n_samples)]
        usecols = [cols[0]] + sample_cols
    chunks = []
    for chunk in pd.read_csv(path, index_col=0, usecols=usecols, chunksize=4000):
        chunk.index = chunk.index.astype(str).str.upper()
        hit = chunk.loc[chunk.index.intersection(keep_genes)]
        if len(hit):
            chunks.append(hit)
    if not chunks:
        return pd.DataFrame()
    mat = pd.concat(chunks)
    mat = mat[~mat.index.duplicated(keep="first")].T
    mat.index = mat.index.astype(str)
    return mat.apply(pd.to_numeric, errors="coerce").fillna(0)


def activity_from_expression(mat: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """PROGENy + CollecTRI. Falls back to gene means if decoupler is missing."""
    try:
        import decoupler as dc
        net = dc.op.progeny(organism="human", top=500)
        tf_net = dc.op.collectri(organism="human")
        X = mat.copy()
        X.columns = X.columns.astype(str).str.upper()
        pw_res = dc.mt.mlm(X, net)
        pw = pd.DataFrame(pw_res[0] if isinstance(pw_res, tuple) else pw_res)
        if list(pw.columns) == list(X.index):
            pw = pw.T
        pw.index = X.index
        tf_res = dc.mt.ulm(X, tf_net)
        tf = pd.DataFrame(tf_res[0] if isinstance(tf_res, tuple) else tf_res)
        if list(tf.columns) == list(X.index):
            tf = tf.T
        tf.index = X.index
        return pw, tf
    except Exception:
        est = [g for g in ("ESR1", "PGR", "FOXA1", "GATA3") if g in mat.columns]
        pw = pd.DataFrame({"Estrogen": mat[est].mean(1) if est else mat.mean(1)}, index=mat.index)
        tf = pw.rename(columns={"Estrogen": "ESR1"})
        return pw, tf


def index_drug_for_row(row: pd.Series) -> str:
    """Pick the drug whose mechanism matches recorded treatment."""
    if float(row.get("her2_status") or 0) == 1:
        return "lapatinib"
    if float(row.get("endocrine_treated") or 0) == 1:
        return "tamoxifen"
    if float(row.get("chemo_treated") or 0) == 1:
        return "paclitaxel"
    return "tamoxifen"


def pathway_for_target(gene: str) -> str:
    return TARGET_TO_PROGENY.get(str(gene).upper(), "MAPK")
