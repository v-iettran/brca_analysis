#!/usr/bin/env python3
"""Host-only job: stream the 33 GB GCTX file once and persist a compact
breast-cell-line compound matrix for runtime List 1 / List 2 scoring.

The API never mounts the raw GCTX. This job keeps only ``trt_cp`` signatures
from a curated breast panel and the gene columns needed for signature queries.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_core.config import (
    COMPACT_GCTX_DIR,
    COMPACT_GCTX_MATRIX,
    COMPACT_GCTX_META,
    FINAL_PROJECT_ROOT,
    METABRIC_DIR,
    MOFA_CLUSTERS_DIR,
)

GCTX_PATH = Path(os.environ.get("GCTX_PATH", FINAL_PROJECT_ROOT / "level5_beta_trt_cp_n720216x12328.gctx"))
SIGINFO_PATH = Path(os.environ.get("SIGINFO_PATH", FINAL_PROJECT_ROOT / "siginfo_beta.txt"))
COMPOUNDINFO_PATH = Path(
    os.environ.get("COMPOUNDINFO_PATH", FINAL_PROJECT_ROOT / "compoundinfo_beta.txt")
)

BREAST_CELL_IDS = {
    "MCF7",
    "MDAMB231",
    "MDA-MB-231",
    "BT549",
    "BT-549",
    "HS578T",
    "HS578T",
    "T47D",
    "T-47D",
    "SKBR3",
    "SK-BR-3",
    "BT474",
    "BT-474",
    "MDAMB468",
    "MDA-MB-468",
    "MDAMB436",
    "HCC38",
    "HCC70",
    "HCC1954",
    "HCC1143",
    "HCC1187",
    "HCC1419",
    "HCC1428",
    "HCC1500",
    "HCC1569",
    "HCC1599",
    "HCC1806",
    "HCC1937",
    "HCC202",
    "HCC2218",
    "HCC70",
    "ZR75B",
    "ZR751",
    "ZR75-1",
}


def _normalize_cell(cell: str) -> str:
    return str(cell).upper().replace("-", "").replace(" ", "").replace("_", "")


def _hugo_to_entrez() -> pd.Series:
    path = METABRIC_DIR / "data_mrna_illumina_microarray.txt"
    raw = pd.read_csv(path, sep="\t", comment="#", usecols=["Hugo_Symbol", "Entrez_Gene_Id"])
    raw = raw.dropna().drop_duplicates(subset="Hugo_Symbol")
    raw["Hugo_Symbol"] = raw["Hugo_Symbol"].str.strip().str.upper()
    return raw.set_index("Hugo_Symbol")["Entrez_Gene_Id"].astype(int)


def _signature_genes() -> set[str]:
    genes: set[str] = set()
    for path in MOFA_CLUSTERS_DIR.glob("cluster_*_signature.csv"):
        sig = pd.read_csv(path)
        genes.update(sig["gene"].astype(str).str.upper().tolist())
    return genes


def main() -> None:
    import h5py

    if not GCTX_PATH.exists():
        raise FileNotFoundError(
            f"GCTX not found at {GCTX_PATH}. This host-only job requires the raw file."
        )

    print("Loading siginfo / compoundinfo ...")
    siginfo = pd.read_csv(SIGINFO_PATH, sep="\t")
    siginfo = siginfo[siginfo["pert_type"] == "trt_cp"].copy()
    siginfo["cell_norm"] = siginfo["cell_iname"].map(_normalize_cell)
    breast_norm = {_normalize_cell(c) for c in BREAST_CELL_IDS}
    siginfo = siginfo[siginfo["cell_norm"].isin(breast_norm)].set_index("sig_id")
    print(f"  breast trt_cp signatures: {len(siginfo)}")

    compoundinfo = pd.read_csv(COMPOUNDINFO_PATH, sep="\t")
    compoundinfo["cmap_name_lower"] = compoundinfo["cmap_name"].str.lower()
    targets_by_name = (
        compoundinfo[compoundinfo["target"].notna() & (compoundinfo["target"] != '""')]
        .groupby("cmap_name_lower")["target"]
        .apply(lambda s: ";".join(sorted(set(s))))
    )

    hugo_to_entrez = _hugo_to_entrez()
    wanted_genes = sorted(_signature_genes() & set(hugo_to_entrez.index))
    wanted_entrez = [int(hugo_to_entrez[g]) for g in wanted_genes]
    print(f"  gene columns retained: {len(wanted_genes)}")

    print(f"Opening {GCTX_PATH} ...")
    with h5py.File(GCTX_PATH, "r") as handle:
        row_ids = np.array(handle["0/META/ROW/id"]).astype(str)
        col_ids = np.array(handle["0/META/COL/id"]).astype(str)
        # GCTX orientation can vary; detect whether rows are genes or signatures.
        if len(row_ids) < len(col_ids):
            gene_ids = row_ids
            sig_ids = col_ids
            genes_are_rows = True
        else:
            # Sometimes genes are columns.
            gene_ids = col_ids
            sig_ids = row_ids
            genes_are_rows = False

        gene_entrez = []
        for gid in gene_ids:
            try:
                gene_entrez.append(int(float(gid)))
            except ValueError:
                gene_entrez.append(-1)
        gene_entrez = np.array(gene_entrez)

        sig_index = pd.Index(sig_ids.astype(str))
        # Build once: reconstructing this 720k-entry set inside the
        # comprehension makes extraction effectively quadratic.
        sig_id_set = set(sig_index)
        keep_sigs = [s for s in siginfo.index.astype(str) if s in sig_id_set]
        print(f"  matched breast signatures in GCTX: {len(keep_sigs)}")
        if not keep_sigs:
            raise RuntimeError("No breast signatures matched GCTX column/row ids.")

        gene_mask = np.isin(gene_entrez, wanted_entrez)
        gene_pos = np.where(gene_mask)[0]
        entrez_to_hugo = {int(hugo_to_entrez[g]): g for g in wanted_genes}
        hugo_cols = [entrez_to_hugo[int(gene_entrez[i])] for i in gene_pos]

        data = handle["0/DATA/0/matrix"]
        if data.shape == (len(sig_ids), len(gene_ids)):
            signatures_are_rows = True
        elif data.shape == (len(gene_ids), len(sig_ids)):
            signatures_are_rows = False
        else:
            raise RuntimeError(
                f"Unexpected GCTX matrix shape {data.shape}; "
                f"metadata has {len(sig_ids)} signatures and {len(gene_ids)} genes."
            )

        # Build matrix signatures x genes. Allocate once to avoid keeping a
        # list of ~4 GB chunks and then duplicating it with np.vstack.
        matrix = np.empty((len(keep_sigs), len(hugo_cols)), dtype=data.dtype)
        batch = 500
        keep_positions = [sig_index.get_loc(s) for s in keep_sigs]
        for start in range(0, len(keep_positions), batch):
            batch_pos = keep_positions[start : start + batch]
            # h5py fancy indices must be monotonically increasing. Read the
            # sorted positions, then restore the siginfo order in memory.
            order = np.argsort(batch_pos)
            sorted_pos = np.asarray(batch_pos, dtype=int)[order]
            inverse_order = np.argsort(order)
            if signatures_are_rows:
                raw = np.asarray(data[sorted_pos, :])
                block = raw[:, gene_pos]
            else:
                raw = np.asarray(data[:, sorted_pos])
                block = raw[gene_pos, :].T
            block = block[inverse_order]
            matrix[start : start + len(batch_pos), :] = block
            print(f"  read signatures {start}..{start + len(batch_pos)}")

    matrix_df = pd.DataFrame(matrix, index=keep_sigs, columns=hugo_cols)
    meta = siginfo.loc[keep_sigs].copy()
    meta["drug"] = meta["pert_iname"] if "pert_iname" in meta.columns else meta.get("cmap_name")
    if "pert_iname" not in meta.columns and "cmap_name" in meta.columns:
        meta["drug"] = meta["cmap_name"]
    if "drug" not in meta.columns or meta["drug"].isna().all():
        # fallback column names across LINCS releases
        for candidate in ("pert_idose", "nearest_dose", "cmap_name", "pert_id"):
            if candidate in meta.columns:
                meta["drug"] = meta[candidate]
                break
    meta["drug"] = meta["drug"].astype(str)
    meta["cell_id"] = meta["cell_iname"]
    meta["targets"] = meta["drug"].str.lower().map(targets_by_name)

    COMPACT_GCTX_DIR.mkdir(parents=True, exist_ok=True)
    matrix_df.to_parquet(COMPACT_GCTX_MATRIX)
    meta.reset_index().rename(columns={"sig_id": "sig_id"}).to_parquet(COMPACT_GCTX_META)
    print(f"Wrote {COMPACT_GCTX_MATRIX} shape={matrix_df.shape}")
    print(f"Wrote {COMPACT_GCTX_META} rows={len(meta)}")


if __name__ == "__main__":
    main()
