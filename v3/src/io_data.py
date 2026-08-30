"""Loaders for the archives dropped into v3/data/raw/.

BayesPrism is the memory-bound stage (genes × cells × types). CARNIVAL is
throughput. The ODE is FLOPs. Subsampling here is only for the first of those.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd

WU_MALIGNANT = "Cancer Epithelial"
CBIO_KEEP_FRAGMENTS = (
    "data_mrna_illumina_microarray.txt",
    "data_mrna_seq_v2_rsem.txt",
    "data_clinical_patient.txt",
    "data_clinical_sample.txt",
    "data_cna.txt",
    "data_log2_cna.txt",
    "data_methylation",
    "data_protein_quantification.txt",
    "data_rppa.txt",
    "normals/data_mrna_seq_v2_rsem_normal_samples.txt",
)


def is_html(path: Path) -> bool:
    try:
        head = Path(path).read_bytes()[:64]
    except OSError:
        return False
    return head.lstrip()[:1] == b"<" or b"<html" in head.lower()


def is_real_data_file(path: Path) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    if "placeholder" in path.name.lower() or path.name.startswith("."):
        return False
    if path.stat().st_size <= 1024:
        return False
    if is_html(path):
        return False
    return True


def pick_data_file(folder: Path, *globs: str) -> Path | None:
    folder = Path(folder)
    if not folder.exists():
        return None
    hits: list[Path] = []
    patterns = globs or ("**/*",)
    for pat in patterns:
        hits.extend(p for p in folder.glob(pat) if is_real_data_file(p))
    if not hits:
        hits = [p for p in folder.rglob("*") if is_real_data_file(p)]
    if not hits:
        return None

    def _score(p: Path) -> tuple:
        n = p.name.lower()
        bad = any(t in n for t in ("annot", "attribute", "gtf", "transcript_expression", "readme", "license"))
        good = any(t in n for t in ("gene_expression", ".gct", "counts", "mrna", "raw.tar", "dose_response"))
        return (0 if bad else 1, 1 if good else 0, p.stat().st_size)

    return max(hits, key=_score)


def limit_rows(df: pd.DataFrame, n: int | None, seed: int = 0) -> pd.DataFrame:
    if n is None or n >= len(df):
        return df
    return df.sample(n=int(n), random_state=seed) if n < len(df) else df


def extract_cbioportal(archive: Path, dest: Path) -> Path:
    """Extract only the matrices NB01/NB04/NB08 need from a cBioPortal tar.gz."""
    archive, dest = Path(archive), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        return dest
    already = list(dest.rglob("data_clinical_patient.txt")) + list(dest.rglob("data_mrna*.txt"))
    if already:
        return dest
    with tarfile.open(archive, "r:gz") as tf:
        members = [
            m for m in tf.getmembers()
            if m.isfile() and any(frag in m.name for frag in CBIO_KEEP_FRAGMENTS)
        ]
        tf.extractall(dest, members=members)
    return dest


def read_gct(path: Path) -> pd.DataFrame:
    """Return samples × genes from a GCT (optionally .gz). Gene index is the Description symbol."""
    path = Path(path)
    df = pd.read_csv(path, sep="\t", skiprows=2, compression="gzip" if str(path).endswith(".gz") else None)
    name_col, desc_col = df.columns[0], df.columns[1]
    genes = df[desc_col].astype(str).str.upper()
    mat = df.drop(columns=[name_col, desc_col])
    mat.index = genes
    mat = mat.groupby(mat.index).mean()
    return mat.T.apply(pd.to_numeric, errors="coerce")


def _load_wu_sample(inner: tarfile.TarFile, genes_keep: list[str] | None, keep_cells: set[str]):
    names = inner.getnames()
    meta_n = next(n for n in names if n.endswith("metadata.csv"))
    gene_n = next(n for n in names if n.endswith("count_matrix_genes.tsv"))
    bar_n = next(n for n in names if n.endswith("count_matrix_barcodes.tsv"))
    mtx_n = next(n for n in names if n.endswith("count_matrix_sparse.mtx"))
    barcodes = [ln.strip() for ln in inner.extractfile(bar_n).read().decode().splitlines() if ln.strip()]
    genes = [ln.strip().split("\t")[0] for ln in inner.extractfile(gene_n).read().decode().splitlines() if ln.strip()]
    genes_u = [g.upper() for g in genes]
    cell_mask = np.array([b in keep_cells for b in barcodes])
    if not cell_mask.any():
        return None
    from scipy.io import mmread

    mtx_bytes = inner.extractfile(mtx_n).read()
    mtx = mmread(io.BytesIO(mtx_bytes)).tocsr()
    # mtx is genes × cells (Matrix Market from Seurat exports)
    if mtx.shape[0] == len(genes) and mtx.shape[1] == len(barcodes):
        sub = mtx[:, cell_mask]
        kept_barcodes = [b for b, k in zip(barcodes, cell_mask) if k]
        if genes_keep is not None:
            want = {g.upper() for g in genes_keep}
            gmask = np.array([g in want for g in genes_u])
            sub = sub[gmask, :]
            genes_u = [g for g, k in zip(genes_u, gmask) if k]
        dense = np.asarray(sub.T.todense(), dtype=np.float32)
        return pd.DataFrame(dense, index=kept_barcodes, columns=genes_u)
    # already cells × genes
    sub = mtx[cell_mask, :]
    kept_barcodes = [b for b, k in zip(barcodes, cell_mask) if k]
    if genes_keep is not None:
        want = {g.upper() for g in genes_keep}
        gmask = np.array([g in want for g in genes_u])
        sub = sub[:, gmask]
        genes_u = [g for g, k in zip(genes_u, gmask) if k]
    dense = np.asarray(sub.todense(), dtype=np.float32)
    return pd.DataFrame(dense, index=kept_barcodes, columns=genes_u)


def wu_celltype_table(archive: Path) -> pd.DataFrame:
    archive = Path(archive)
    frames = []
    with tarfile.open(archive, "r") as outer:
        for m in outer.getmembers():
            if not m.name.endswith(".tar.gz"):
                continue
            blob = outer.extractfile(m).read()
            inner = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
            meta_n = next(n for n in inner.getnames() if n.endswith("metadata.csv"))
            df = pd.read_csv(inner.extractfile(meta_n))
            id_col = df.columns[0]
            df = df.rename(columns={id_col: "cell_id"})
            frames.append(df[["cell_id", "celltype_major"]])
    meta = pd.concat(frames, ignore_index=True)
    meta["cell_type"] = meta["celltype_major"].astype(str).replace({WU_MALIGNANT: "malignant"})
    return meta


def subsample_wu_cells(meta: pd.DataFrame, n_cells: int | None, seed: int = 0) -> pd.DataFrame:
    if n_cells is None or n_cells >= len(meta):
        return meta
    rng = np.random.default_rng(seed)
    parts = []
    types = meta["cell_type"].value_counts()
    remaining = int(n_cells)
    n_types = len(types)
    for i, (ct, count) in enumerate(types.items()):
        take = remaining if i == n_types - 1 else max(50, int(round(n_cells * count / len(meta))))
        take = min(take, count, remaining)
        idx = meta.index[meta["cell_type"] == ct]
        chosen = rng.choice(idx.to_numpy(), size=take, replace=False)
        parts.append(meta.loc[chosen])
        remaining -= take
        if remaining <= 0:
            break
    out = pd.concat(parts)
    if len(out) > n_cells:
        out = out.sample(n=int(n_cells), random_state=seed)
    return out


def build_wu_reference(
    archive: Path,
    out_ref: Path,
    out_types: Path,
    n_cells: int | None = 25_000,
    genes_keep: list[str] | None = None,
    max_genes: int = 2000,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratified ~n_cells reference, cells × genes, with BayesPrism key 'malignant'."""
    archive = Path(archive)
    meta = wu_celltype_table(archive)
    picked = subsample_wu_cells(meta, n_cells, seed=seed)
    keep_cells = set(picked["cell_id"].astype(str))
    chunks = []
    with tarfile.open(archive, "r") as outer:
        for m in outer.getmembers():
            if not m.name.endswith(".tar.gz"):
                continue
            blob = outer.extractfile(m).read()
            inner = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
            part = _load_wu_sample(inner, genes_keep, keep_cells)
            if part is not None and len(part):
                chunks.append(part)
    if not chunks:
        raise FileNotFoundError(f"No overlapping cells in {archive}")
    ref = pd.concat(chunks, axis=0)
    ref = ref.groupby(ref.index).first()
    if ref.columns.duplicated().any():
        ref = ref.T.groupby(ref.columns).mean().T
    if ref.shape[1] > max_genes:
        var = ref.var(axis=0).nlargest(max_genes).index
        ref = ref[var]
    elif genes_keep is not None:
        cols = [g for g in (c.upper() for c in genes_keep) if g in ref.columns]
        if cols:
            ref = ref[[c for c in cols if c in ref.columns]]
    types_df = picked.set_index("cell_id")[["cell_type"]].reindex(ref.index).dropna()
    ref = ref.loc[types_df.index]
    out_ref.parent.mkdir(parents=True, exist_ok=True)
    ref.index.name = "cell_id"
    ref.to_parquet(out_ref)
    out = types_df.reset_index()
    if "cell_id" not in out.columns:
        out = out.rename(columns={out.columns[0]: "cell_id"})
    out.to_parquet(out_types, index=False)
    return ref, out


def nnls_deconvolution(bulk: pd.DataFrame, ref: pd.DataFrame, types: pd.DataFrame) -> pd.DataFrame:
    """Fast centroid NNLS fallback if BayesPrism is not runnable. Declared, not a substitute."""
    from scipy.optimize import nnls

    types = types.set_index(types.columns[0]) if types.columns[0] != "cell_type" else types
    if "cell_type" not in types.columns:
        types.columns = ["cell_id", "cell_type"] if types.shape[1] == 2 else types.columns
        types = types.set_index("cell_id")
    common = [g for g in bulk.columns if g in ref.columns]
    B = np.log1p(np.clip(bulk[common].fillna(0).to_numpy(float), 0, None))
    cents = []
    labels = []
    for ct, sub in types.groupby("cell_type"):
        cells = [c for c in sub.index if c in ref.index]
        if not cells:
            continue
        cents.append(np.log1p(np.clip(ref.loc[cells, common].mean(0).to_numpy(float), 0, None)))
        labels.append(ct)
    C = np.vstack(cents).T  # genes × types
    rows = []
    for i in range(B.shape[0]):
        x, _ = nnls(C, B[i])
        s = x.sum()
        rows.append((x / s) if s > 0 else x)
    return pd.DataFrame(rows, index=bulk.index, columns=labels)


def parse_geo_series_matrix(path: Path) -> pd.DataFrame:
    """Parse a GEO series_matrix into samples × characteristics (value after ': ')."""
    import gzip

    path = Path(path)
    opener = gzip.open if str(path).endswith(".gz") else open
    geo, titles = None, None
    char_rows: list[list[str]] = []
    with opener(path, "rt", errors="replace") as f:
        for line in f:
            if line.startswith("!Sample_geo_accession"):
                geo = [c.strip().strip('"') for c in line.rstrip("\n").split("\t")[1:]]
            elif line.startswith("!Sample_title"):
                titles = [c.strip().strip('"') for c in line.rstrip("\n").split("\t")[1:]]
            elif line.startswith("!Sample_characteristics_ch1"):
                char_rows.append([c.strip().strip('"') for c in line.rstrip("\n").split("\t")[1:]])
            elif line.startswith("!series_matrix_table_begin"):
                break
    if not geo:
        raise ValueError(f"no !Sample_geo_accession in {path}")
    data: dict[str, list] = {"geo_accession": geo}
    if titles:
        data["title"] = titles
    n = len(geo)
    for row in char_rows:
        row = (row + [""] * n)[:n]
        keys = []
        vals = []
        for cell in row:
            if ":" in cell:
                k, v = cell.split(":", 1)
                keys.append(k.strip().lower())
                vals.append(v.strip())
            else:
                keys.append("")
                vals.append(cell)
        key = next((k for k in keys if k), None)
        if not key:
            continue
        col = key.replace(" ", "_")
        data[col] = vals
    return pd.DataFrame(data)


def load_scanb_clinical(folder: Path) -> pd.DataFrame:
    """Concatenate GSE96058 series matrices (both Illumina platforms)."""
    folder = Path(folder)
    frames = []
    for p in sorted(folder.glob("GSE96058*_series_matrix.txt.gz")):
        frame = parse_geo_series_matrix(p)
        name = p.name.upper()
        frame["platform"] = "GPL18573" if "GPL18573" in name else ("GPL11154" if "GPL11154" in name else "unknown")
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    clin = pd.concat(frames, ignore_index=True)
    for col in (
        "overall_survival_days",
        "overall_survival_event",
        "age_at_diagnosis",
        "tumor_size",
        "er_status",
        "pgr_status",
        "her2_status",
        "ki67_status",
        "nhg",
        "endocrine_treated",
        "chemo_treated",
    ):
        if col in clin.columns:
            clin[col] = pd.to_numeric(clin[col].replace({"NA": np.nan, "": np.nan}), errors="coerce")
    return clin


def load_almanac_pair_scores(
    archive: Path,
    nsc_map: pd.DataFrame | None = None,
    breast_only: bool = True,
) -> pd.DataFrame:
    """Median ComboScore (SCORE) per unordered NSC pair, optionally Breast panel only."""
    import zipfile

    archive = Path(archive)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith((".csv", ".txt")))
            with zf.open(name) as fh:
                raw = pd.read_csv(
                    fh,
                    usecols=lambda c: str(c).upper() in {
                        "NSC1", "NSC2", "SCORE", "PANEL", "VALID", "CELLNAME",
                    },
                    low_memory=False,
                )
    else:
        raw = pd.read_csv(archive, usecols=lambda c: str(c).upper() in {
            "NSC1", "NSC2", "SCORE", "PANEL", "VALID",
        }, low_memory=False)
    raw.columns = [c.upper() for c in raw.columns]
    if "VALID" in raw.columns:
        raw = raw[raw["VALID"].astype(str).str.upper().eq("Y")]
    if breast_only and "PANEL" in raw.columns:
        breast = raw["PANEL"].astype(str).str.contains("Breast", case=False, na=False)
        if breast.any():
            raw = raw[breast]
    raw["SCORE"] = pd.to_numeric(raw["SCORE"], errors="coerce")
    raw["NSC1"] = pd.to_numeric(raw["NSC1"], errors="coerce")
    raw["NSC2"] = pd.to_numeric(raw["NSC2"], errors="coerce")
    raw = raw.dropna(subset=["NSC1", "NSC2", "SCORE"])
    a = np.minimum(raw["NSC1"], raw["NSC2"]).astype(int)
    b = np.maximum(raw["NSC1"], raw["NSC2"]).astype(int)
    pairs = pd.DataFrame({"nsc_a": a, "nsc_b": b, "score": raw["SCORE"].to_numpy()})
    agg = pairs.groupby(["nsc_a", "nsc_b"], as_index=False)["score"].median()
    if nsc_map is None or nsc_map.empty:
        return agg
    from drug_map import normalize_drug_name
    nsc_map = nsc_map.copy()
    if "drug" not in nsc_map.columns and "drug_name" in nsc_map.columns:
        nsc_map["drug"] = nsc_map["drug_name"]
    nsc_map = nsc_map.dropna(subset=["nsc"]).copy()
    nsc_map["nsc"] = pd.to_numeric(nsc_map["nsc"], errors="coerce")
    nsc_map = nsc_map.dropna(subset=["nsc"])
    nsc_map["nsc"] = nsc_map["nsc"].astype(int)
    drug_of = {}
    for _, r in nsc_map.iterrows():
        drug_of.setdefault(int(r["nsc"]), normalize_drug_name(r["drug"]))
    agg["drug_a"] = agg["nsc_a"].map(drug_of)
    agg["drug_b"] = agg["nsc_b"].map(drug_of)
    named = agg.dropna(subset=["drug_a", "drug_b"])
    named = named[named["drug_a"] != named["drug_b"]]
    return named


def encode_er_status(raw: pd.Series) -> pd.Series:
    """ER+ = 1, ER− = 0. Never rank-encode strings (`negative` < `positive`).

    METABRIC writes the typo `Positve`; that still maps to 1.
    """
    s = raw.astype(str).str.strip().str.lower()
    out = pd.Series(np.nan, index=raw.index, dtype=float)
    pos = s.str.contains(r"pos|\+|positive", regex=True, na=False) | s.isin(
        ["1", "1.0", "true", "yes", "er+"]
    )
    neg = s.str.contains(r"neg|negative", regex=True, na=False) | s.isin(
        ["0", "0.0", "false", "no", "er-"]
    )
    # `negative` contains neither `pos` nor `+`; assign neg after pos so
    # a true positive cannot be overwritten.
    out[pos] = 1.0
    out[neg & ~pos] = 0.0
    return out


def load_depmap_breast_expression(
    expr_path: Path,
    model_path: Path,
    n: int | None = None,
) -> pd.DataFrame:
    """Breast cell-line RNA (log1p TPM), one default row per ModelID.

    Used by NB07 so CARNIVAL networks are inferred on the same lines that
    DepMap CRISPR essentiality is measured on — not on tumour samples.
    """
    model = pd.read_csv(model_path)
    breast = set(
        model.loc[
            model["OncotreeLineage"].astype(str).str.contains("Breast", case=False, na=False),
            "ModelID",
        ].astype(str)
    )
    df = pd.read_csv(expr_path)
    if "IsDefaultEntryForModel" in df.columns:
        df = df[df["IsDefaultEntryForModel"].astype(str).str.lower().isin(["yes", "true", "1"])]
    df["ModelID"] = df["ModelID"].astype(str)
    df = df[df["ModelID"].isin(breast)].drop_duplicates("ModelID").sort_values("ModelID")
    if n is not None:
        df = df.head(int(n))
    gene_cols = [c for c in df.columns if isinstance(c, str) and c.endswith(")")]
    mat = df.set_index("ModelID")[gene_cols].apply(pd.to_numeric, errors="coerce")
    mat.columns = mat.columns.str.replace(r" \(\d+\)$", "", regex=True).str.upper()
    if mat.columns.duplicated().any():
        mat = mat.T.groupby(level=0).mean().T
    mat.attrs["n_breast_available"] = int(len(breast))
    return mat.fillna(0)


def canon_drug(name: str) -> str:
    from drug_map import normalize_drug_name
    return normalize_drug_name(name)
