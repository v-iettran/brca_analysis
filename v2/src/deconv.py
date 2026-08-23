"""TCGA count mixtures for BayesPrism, then malignant-compartment harmonisation.

METABRIC is Illumina HT-12 microarray — there are no counts. Do not feed it to
BayesPrism. Phases 2–4 use TCGA only; METABRIC stays the v1 comparison baseline.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from io_data import extract_cbioportal
from transforms import cohort_zscore


def read_cbioportal_matrix(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", comment="#")
    if "Hugo_Symbol" in df.columns:
        df = df.set_index("Hugo_Symbol")
    else:
        df = df.set_index(df.columns[0])
    drop = [c for c in df.columns if "entrez" in c.lower()]
    df = df.drop(columns=drop, errors="ignore").apply(pd.to_numeric, errors="coerce")
    df.index = df.index.astype(str).str.upper()
    if df.index.duplicated().any():
        df = df.groupby(level=0).mean()
    return df.T  # samples × genes


def as_count_like(mat: pd.DataFrame) -> pd.DataFrame:
    """Samples × genes → non-negative count-like matrix.

    Median < 20 is treated as log2 intensity (METABRIC microarray) and
    exponentiated with 2**x. Otherwise values are already counts (TCGA RSEM).
    """
    X = mat.apply(pd.to_numeric, errors="coerce")
    X.index = X.index.astype(str)
    X.columns = X.columns.astype(str).str.upper()
    if X.columns.duplicated().any():
        X = X.T.groupby(level=0).mean().T
    vals = X.to_numpy(dtype=float)
    med = float(np.nanmedian(vals))
    if np.isnan(med):
        med = 0.0
    if med < 20:
        out = np.exp(np.log(2.0) * np.clip(vals, 0, None))
        src = "log2_to_2p"
    else:
        out = np.clip(vals, 0, None)
        src = "linear_counts"
    df = pd.DataFrame(out, index=X.index, columns=X.columns).fillna(0)
    df.attrs["count_source"] = src
    return df


def euro_float(series: pd.Series) -> pd.Series:
    """Parse `0,9246` (TCGAbiolinks Tumor.purity export) or ordinary floats."""
    s = series.astype(str).str.replace(",", ".", regex=False)
    s = s.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})
    return pd.to_numeric(s, errors="coerce")


def load_aran_cpe(path: Path) -> pd.DataFrame:
    """Aran 2015 CPE/ABSOLUTE table. Index = TCGA 12-char barcode."""
    df = pd.read_csv(path)
    colmap = {c.lower().replace(" ", "").replace(".", ""): c for c in df.columns}
    sid = colmap.get("sampleid") or colmap.get("sample") or df.columns[0]
    out = pd.DataFrame({"sample": df[sid].astype(str)})
    out["barcode12"] = out["sample"].str[:12]
    for name, keys in {
        "CPE": ("cpe",),
        "ABSOLUTE": ("absolute",),
        "ESTIMATE": ("estimate",),
        "cancer_type": ("cancertype", "cancer.type"),
    }.items():
        src = next((colmap[k] for k in keys if k in colmap), None)
        if src is None:
            continue
        out[name] = df[src] if name == "cancer_type" else euro_float(df[src])
    return out.dropna(subset=["barcode12"]).drop_duplicates("barcode12").set_index("barcode12")


def purity_spearman_with_null(
    malignant: pd.Series,
    purity: pd.Series,
    n_perm: int = 1000,
    seed: int = 0,
) -> dict:
    """Join-aligned Spearman plus a permutation null for the same pairs."""
    from scipy.stats import spearmanr

    pair = pd.concat(
        [malignant.rename("mal"), purity.rename("pur")], axis=1, join="inner"
    ).dropna()
    n = int(len(pair))
    if n < 10 or pair["pur"].nunique() < 2 or pair["mal"].nunique() < 2:
        return {"n": n, "rho": float("nan"), "null_mean": float("nan"), "null_sd": float("nan"), "p": float("nan")}
    mal = pair["mal"].to_numpy(dtype=float)
    pur = pair["pur"].to_numpy(dtype=float)
    rho = float(spearmanr(mal, pur).statistic)
    rng = np.random.default_rng(seed)
    null = np.array([float(spearmanr(mal, rng.permutation(pur)).statistic) for _ in range(int(n_perm))])
    p = float((np.abs(null) >= abs(rho)).mean())
    return {
        "n": n,
        "rho": rho,
        "null_mean": float(null.mean()),
        "null_sd": float(null.std()),
        "p": p,
    }


def load_bulk_count_cohorts(raw: Path) -> dict[str, pd.DataFrame]:
    """TCGA RSEM counts for BayesPrism. METABRIC microarray is recorded, not deconvolved."""
    raw = Path(raw)
    extract_cbioportal(raw / "metabric" / "brca_metabric.tar.gz", raw / "metabric" / "extracted")
    extract_cbioportal(raw / "tcga_brca" / "brca_tcga_pan_can_atlas_2018.tar.gz", raw / "tcga_brca" / "extracted")
    out: dict[str, pd.DataFrame] = {}
    m = next((raw / "metabric").rglob("data_mrna_illumina_microarray.txt"), None)
    if m is not None:
        out["METABRIC"] = as_count_like(read_cbioportal_matrix(m))
    t = next((raw / "tcga_brca").rglob("data_mrna_seq_v2_rsem.txt"), None)
    if t is not None and "normal" not in str(t).lower():
        mat = as_count_like(read_cbioportal_matrix(t))
        mat.index = mat.index.astype(str).str[:12]
        out["TCGA"] = mat
    return out


def harmonise_malignant(Z: pd.DataFrame, cohort: pd.Series) -> pd.DataFrame:
    """log1p then per-cohort z-score — harmonise the malignant compartment, not bulk."""
    X = np.log1p(np.clip(Z.to_numpy(dtype=float), 0, None))
    out = np.zeros_like(X)
    aligned = cohort.reindex(Z.index)
    for c in pd.unique(aligned.dropna()):
        m = (aligned == c).to_numpy()
        if m.sum() < 2:
            out[m] = X[m]
            continue
        out[m] = cohort_zscore(X[m])
    missing = aligned.isna().to_numpy()
    if missing.any():
        out[missing] = cohort_zscore(X[missing]) if missing.sum() > 1 else X[missing]
    return pd.DataFrame(out, index=Z.index, columns=Z.columns)


def run_bayesprism_chunks(
    bulk: pd.DataFrame,
    r_script: Path,
    ref_p: Path,
    ct_p: Path,
    outdir: Path,
    chunk: int = 40,
    cores: int = 2,
    timeout: int = 1200,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, str]:
    """Chunked BayesPrism. Returns (theta, Z_malignant, note)."""
    from io_data import nnls_deconvolution

    thetas, zs = [], []
    r_ok = False
    for start in range(0, len(bulk), chunk):
        piece = bulk.iloc[start:start + chunk]
        mix_p = outdir / "mixture.parquet"
        piece.to_parquet(mix_p)
        cmd = [
            "Rscript", str(r_script),
            "--reference", str(ref_p),
            "--mixture", str(mix_p),
            "--celltypes", str(ct_p),
            "--outdir", str(outdir),
            "--cores", str(cores),
        ]
        print("BayesPrism chunk", start, "n=", len(piece), flush=True)
        try:
            rc = subprocess.run(cmd, check=False, timeout=timeout, capture_output=True, text=True)
            if rc.returncode != 0:
                print("R stderr:", (rc.stderr or "")[-2000:])
        except subprocess.TimeoutExpired:
            print("BayesPrism timed out; NNLS fallback")
            rc = type("R", (), {"returncode": 1})()
        if rc.returncode == 0 and (outdir / "theta.parquet").exists():
            t = pd.read_parquet(outdir / "theta.parquet")
            t.index = piece.index[: len(t)]
            thetas.append(t)
            if (outdir / "Z_malignant.parquet").exists():
                z = pd.read_parquet(outdir / "Z_malignant.parquet")
                z.index = piece.index[: len(z)]
                zs.append(z)
            r_ok = True
        else:
            print("R BayesPrism failed for chunk; will use NNLS fallback")
            break
    if r_ok and thetas:
        theta = pd.concat(thetas)
        Z_mal = pd.concat(zs) if zs else bulk.loc[theta.index]
        return theta, Z_mal, f"BayesPrism n_bulk={len(theta)}"
    cts = pd.read_parquet(ct_p)
    ref = pd.read_parquet(ref_p)
    theta = nnls_deconvolution(bulk, ref, cts)
    return theta, bulk.loc[theta.index], f"NNLS fallback (declared) n_bulk={len(theta)}"
