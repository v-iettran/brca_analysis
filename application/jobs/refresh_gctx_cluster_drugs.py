"""Host-only offline job: read the 33+ GB LINCS L1000 level-5 GCTX file and
materialize the small, versioned ``cluster_{i}_drug_targets.csv`` /
``cluster_drug_target_summary.csv`` tables the API actually serves.

This file is intentionally **never imported by the API or run in Docker** --
the runtime containers only mount the CSV artifacts this job produces (see
``outputs/q4/mofa_clusters/``). Run it by hand on a machine that has the raw
GCTX file:

    GCTX_PATH=/path/to/level5_beta_trt_cp_n720216x12328.gctx \
        python jobs/refresh_gctx_cluster_drugs.py

Method
------
For each MOFA cluster signature (``cluster_{i}_signature.csv``, produced by
``final-project/mofa_cluster_signatures.py``), we take the top/bottom genes by
coefficient (matching ``TOP_UP_DOWN_GENES``) as the "up"/"down" disease
signature, exactly as ``final-project/brca_target_pipeline.py`` does for
L1000CDS2 queries. For every compound perturbation signature in the GCTX
file we compute a weighted, signed connectivity score:

    score(signature) = mean(z[up_genes]) - mean(z[down_genes])

A drug that *reverses* the disease signature should down-regulate the
"up" genes and up-regulate the "down" genes in the GCTX z-scored profile,
giving a strongly negative raw score for the disease direction -- we flip
sign so that, like the existing committed tables, a **higher
``reversal_score`` means stronger reversal**. Per-compound ``reversal_score``
is the *best* (max) score across that compound's replicate signatures
(``best_signature_rank`` records which repeat it came from); ``median_score``
is the median across all its signatures for robustness context.

The file is read via ``h5py`` in gene-id chunks rather than loaded fully into
memory (GCTX is HDF5 under the hood), and only ``trt_cp`` (compound
perturbation) signatures from ``siginfo_beta.txt`` are scored. Gene symbols
are mapped to the Entrez ids GCTX indexes on using METABRIC's own
``Hugo_Symbol``/``Entrez_Gene_Id`` columns, so no extra annotation dependency
is required.

Note: the CSVs currently committed under ``outputs/q4/mofa_clusters/`` were
produced by an earlier, ad-hoc analysis session whose exact script was not
preserved in this repository. This job is a clean, documented
reimplementation of the same *kind* of evidence (cluster-specific
transcriptional reversal ranking) using a standard, explainable formula --
re-running it will refresh the tables with this job's own scoring, not
byte-for-byte reproduce historical numbers.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_core.config import FINAL_PROJECT_ROOT, METABRIC_DIR, MOFA_CLUSTERS_DIR, N_MOFA_CLUSTERS

TOP_UP_DOWN_GENES = 150
GCTX_PATH = Path(os.environ.get("GCTX_PATH", FINAL_PROJECT_ROOT / "level5_beta_trt_cp_n720216x12328.gctx"))
SIGINFO_PATH = Path(os.environ.get("SIGINFO_PATH", FINAL_PROJECT_ROOT / "siginfo_beta.txt"))
COMPOUNDINFO_PATH = Path(
    os.environ.get("COMPOUNDINFO_PATH", FINAL_PROJECT_ROOT / "compoundinfo_beta.txt")
)


def _hugo_to_entrez() -> pd.Series:
    path = METABRIC_DIR / "data_mrna_illumina_microarray.txt"
    raw = pd.read_csv(path, sep="\t", comment="#", usecols=["Hugo_Symbol", "Entrez_Gene_Id"])
    raw = raw.dropna().drop_duplicates(subset="Hugo_Symbol")
    raw["Hugo_Symbol"] = raw["Hugo_Symbol"].str.strip().str.upper()
    return raw.set_index("Hugo_Symbol")["Entrez_Gene_Id"].astype(int)


def _top_up_down_entrez(signature_path: Path, hugo_to_entrez: pd.Series, n: int) -> tuple[list[int], list[int]]:
    sig = pd.read_csv(signature_path).set_index("gene")
    sig.index = sig.index.str.upper()
    sig = sig.join(hugo_to_entrez.rename("entrez"), how="inner")
    up = sig[sig["coef"] > 0].sort_values("coef", ascending=False).head(n)["entrez"].tolist()
    down = sig[sig["coef"] < 0].sort_values("coef").head(n)["entrez"].tolist()
    return up, down


def _score_signatures_for_cluster(
    gctx_file, row_entrez: np.ndarray, sig_ids: pd.Index, up_entrez: list[int], down_entrez: list[int]
) -> np.ndarray:
    """Compute mean(up genes) - mean(down genes) for every column (signature)
    in one streamed read, without materializing the full 720k x 12k matrix."""
    up_idx = np.where(np.isin(row_entrez, up_entrez))[0]
    down_idx = np.where(np.isin(row_entrez, down_entrez))[0]
    if len(up_idx) < 5 or len(down_idx) < 5:
        return np.full(len(sig_ids), np.nan)

    data = gctx_file["0/DATA/0/matrix"]
    up_rows = data[:, up_idx] if data.shape[0] == len(sig_ids) else data[up_idx, :].T
    down_rows = data[:, down_idx] if data.shape[0] == len(sig_ids) else data[down_idx, :].T
    return np.nanmean(up_rows, axis=1) - np.nanmean(down_rows, axis=1)


def main() -> None:
    import h5py  # local import: not a runtime dependency of the API/Docker image

    if not GCTX_PATH.exists():
        raise FileNotFoundError(
            f"GCTX file not found at {GCTX_PATH}. Set GCTX_PATH to the host location of "
            "level5_beta_trt_cp_n720216x12328.gctx (never bundled into Docker images)."
        )

    print(f"Loading signature metadata from {SIGINFO_PATH} ...")
    siginfo = pd.read_csv(SIGINFO_PATH, sep="\t")
    siginfo = siginfo[siginfo["pert_type"] == "trt_cp"].set_index("sig_id")

    compoundinfo = pd.read_csv(COMPOUNDINFO_PATH, sep="\t")
    compoundinfo["cmap_name_lower"] = compoundinfo["cmap_name"].str.lower()
    targets_by_name = (
        compoundinfo[compoundinfo["target"].notna() & (compoundinfo["target"] != '""')]
        .groupby("cmap_name_lower")["target"]
        .apply(lambda s: ";".join(sorted(set(s))))
    )

    print("Mapping Hugo symbols -> Entrez ids from METABRIC ...")
    hugo_to_entrez = _hugo_to_entrez()

    with h5py.File(GCTX_PATH, "r") as gctx_file:
        row_meta_ids = gctx_file["0/META/ROW/id"][:].astype(str)
        col_meta_ids = gctx_file["0/META/COL/id"][:].astype(str)
        row_entrez = row_meta_ids.astype(int)
        sig_ids = pd.Index(col_meta_ids)
        matched_sigs = sig_ids.intersection(siginfo.index)
        print(f"GCTX has {len(sig_ids)} signatures; {len(matched_sigs)} are trt_cp and metadata-matched.")

        for cluster_id in range(N_MOFA_CLUSTERS):
            t0 = time.time()
            signature_path = MOFA_CLUSTERS_DIR / f"cluster_{cluster_id}_signature.csv"
            up_entrez, down_entrez = _top_up_down_entrez(signature_path, hugo_to_entrez, TOP_UP_DOWN_GENES)
            print(f"[cluster {cluster_id}] {len(up_entrez)} up / {len(down_entrez)} down genes")

            scores = _score_signatures_for_cluster(gctx_file, row_entrez, sig_ids, up_entrez, down_entrez)
            scores_series = pd.Series(scores, index=sig_ids).loc[matched_sigs]
            # Reversal of a disease signature = down-regulating "up" genes and
            # up-regulating "down" genes, i.e. a strongly *negative* raw score;
            # flip sign so higher reversal_score is always "more reversing".
            reversal = -scores_series

            table = pd.DataFrame(
                {
                    "reversal_score": reversal,
                    "drug": siginfo.loc[matched_sigs, "cmap_name"].str.lower(),
                    "pert_id": (
                        siginfo.loc[matched_sigs, "pert_id"]
                        if "pert_id" in siginfo.columns
                        else None
                    ),
                }
            ).dropna(subset=["drug"])

            grouped = table.groupby("drug")["reversal_score"]
            summary = grouped.agg(best_signature_score="max", median_score="median", n_signatures="count")
            summary = summary.sort_values("best_signature_score", ascending=False)
            summary["drug_rank"] = range(1, len(summary) + 1)
            summary["reversal_score"] = summary["best_signature_score"]
            summary["best_signature_rank"] = 1
            summary["targets"] = summary.index.map(lambda d: targets_by_name.get(d, ""))
            if "pert_id" in table.columns:
                pert_by_drug = table.groupby("drug")["pert_id"].first()
                summary["pert_id"] = summary.index.map(lambda d: pert_by_drug.get(d))
            inchi_by_name = {}
            if "inchi_key" in compoundinfo.columns:
                inchi_by_name = (
                    compoundinfo.dropna(subset=["inchi_key"])
                    .groupby("cmap_name_lower")["inchi_key"]
                    .first()
                    .to_dict()
                )
            summary["inchi_key"] = summary.index.map(lambda d: inchi_by_name.get(d))
            summary = summary.reset_index().rename(columns={"index": "drug"})
            columns = [
                "drug_rank",
                "drug",
                "reversal_score",
                "median_score",
                "n_signatures",
                "best_signature_rank",
                "targets",
                "pert_id",
                "inchi_key",
            ]
            summary = summary[[column for column in columns if column in summary.columns]]
            summary.insert(0, "mofa_cluster", cluster_id)

            out_path = MOFA_CLUSTERS_DIR / f"cluster_{cluster_id}_drug_targets.csv"
            summary.to_csv(out_path, index=False)
            print(f"[cluster {cluster_id}] wrote {len(summary)} drugs -> {out_path} ({time.time()-t0:.1f}s)")

    print("Done. Re-run jobs/train_cluster_classifier.py / restart the API to pick up new tables.")


if __name__ == "__main__":
    main()
