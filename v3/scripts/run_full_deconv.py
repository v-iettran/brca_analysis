#!/usr/bin/env python3
"""Full-scale TCGA-BRCA BayesPrism. No sample cap, no NNLS fallback, no padding."""

from __future__ import annotations

import gc
import json
import resource
import sys
import time
from pathlib import Path

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from deconv import (  # noqa: E402
    harmonise_malignant,
    load_aran_cpe,
    load_bulk_count_cohorts,
    purity_spearman_with_null,
    run_bayesprism_chunks,
)
from gate import gate  # noqa: E402
from io_data import build_wu_reference, pick_data_file  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CHUNK = 150
N_SC_CELLS = 25_000
PURITY_MIN = 0.65
TIMEOUT = 6 * 60 * 60
CORES = 2


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


def main() -> int:
    raw = V2_ROOT / "data" / "raw"
    interim = V2_ROOT / "data" / "interim"
    ref_dir = V2_ROOT / "data" / "reference"
    out_bp = interim / "bayesprism_full"
    out_bp.mkdir(parents=True, exist_ok=True)
    r_script = V2_ROOT / "notebooks" / "r" / "run_bayesprism.R"
    log_p = out_bp / "progress.jsonl"

    def log(event: dict) -> None:
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rss_mb": round(rss_mb(), 1), **event}
        with log_p.open("a") as f:
            f.write(json.dumps(event) + "\n")
        print(event, flush=True)

    wu = pick_data_file(raw / "wu_scrna", "*.tar", "*.tar.gz")
    cohorts = load_bulk_count_cohorts(raw)
    tcga = cohorts.get("TCGA")
    if tcga is None:
        log({"status": "stop", "reason": "TCGA RSEM matrix missing"})
        return 2
    if wu is None:
        log({"status": "stop", "reason": "Wu scRNA archive missing — not substituting bulk"})
        return 2

    n_full = len(tcga)
    log({"status": "start", "n_tcga": n_full, "n_genes": int(tcga.shape[1]), "chunk": CHUNK, "n_sc": N_SC_CELLS})
    if n_full < 800:
        log({"status": "stop", "reason": f"TCGA n={n_full} is below the expected ~1100 — not a silent cap, check the matrix"})
        return 2

    genes = list(tcga.var().nlargest(min(2500, tcga.shape[1])).index)
    ref_p, ct_p = out_bp / "reference.parquet", out_bp / "celltypes.parquet"
    gene_file = out_bp / "reference_genes.txt"
    if not (ref_p.exists() and ct_p.exists() and gene_file.exists() and gene_file.read_text().splitlines() == genes):
        log({"status": "building_reference", "n_cells": N_SC_CELLS, "n_genes": len(genes)})
        build_wu_reference(wu, ref_p, ct_p, n_cells=N_SC_CELLS, genes_keep=genes, max_genes=2500)
        gene_file.write_text("\n".join(genes))
    ref = pd.read_parquet(ref_p)
    log({"status": "reference_ready", "ref_shape": list(ref.shape)})
    common = [g for g in tcga.columns if g in ref.columns]
    mix = tcga.loc[:, common]
    log({"status": "mixture_ready", "mix_shape": list(mix.shape)})

    t0 = time.time()
    try:
        theta, z_counts, note = run_bayesprism_chunks(
            mix,
            r_script,
            ref_p,
            ct_p,
            out_bp,
            chunk=CHUNK,
            cores=CORES,
            timeout=TIMEOUT,
            allow_nnls_fallback=False,
        )
    except RuntimeError as exc:
        log({"status": "stop", "reason": str(exc), "elapsed_s": round(time.time() - t0, 1)})
        return 3

    if theta is None or len(theta) < n_full:
        log({
            "status": "stop",
            "reason": f"partial BayesPrism n={0 if theta is None else len(theta)}/{n_full}",
            "note": note,
        })
        return 3

    theta["cohort"] = "TCGA"
    cohort_tag = pd.Series("TCGA", index=z_counts.index)
    z_mal = harmonise_malignant(z_counts, cohort_tag)
    theta.to_parquet(interim / "deconvolution_posterior.parquet")
    z_mal.to_parquet(interim / "intrinsic_expression.parquet")
    z_counts.to_parquet(interim / "intrinsic_expression_counts.parquet")
    cohort_tag.to_frame("cohort").to_parquet(interim / "intrinsic_sample_cohort.parquet")
    log({"status": "wrote_intrinsic", "n": int(len(z_mal)), "p": int(z_mal.shape[1]), "note": note})

    mal_col = [c for c in theta.columns if str(c).lower().startswith("malig")][0]
    mal = theta[mal_col].astype(float)
    mal.index = mal.index.astype(str).str[:12]
    cpe = load_aran_cpe(ref_dir / "tcga_aran_cpe.csv")
    if "cancer_type" in cpe.columns:
        cpe = cpe[cpe["cancer_type"].astype(str).str.upper().eq("BRCA")]
    stats = purity_spearman_with_null(mal, cpe["CPE"], n_perm=1000, seed=0)
    ids = list(mal.index)
    gate(
        "NB02",
        "purity_concordance",
        float(stats["rho"]) if stats["rho"] == stats["rho"] else 0.0,
        PURITY_MIN,
        n=int(stats["n"]),
        min_n=20,
        smoke_test=False,
        sample_ids=ids,
        note=(
            f"vs Aran CPE n={stats['n']} rho={stats['rho']:.3f} "
            f"shuffle_mean={stats['null_mean']:.3f} p={stats['p']:.3f} "
            f"TCGA:{note} n_bulk={len(theta)} n_cells={len(ref)} source=tcga_counts_only"
        ),
    )
    (interim / "NB02_purity_diagnostics.json").write_text(json.dumps({"cpe": stats, "n_full": n_full}, indent=2))
    log({"status": "done", "n": int(len(theta)), "purity_n": int(stats["n"]), "rho": stats["rho"]})
    gc.collect()
    after = V2_ROOT / "scripts" / "run_full_v3_after_deconv.py"
    log({"status": "starting_downstream", "script": str(after)})
    import subprocess

    rc = subprocess.run(
        [sys.executable, str(after)],
        cwd=str(V2_ROOT.parent),
        env={**__import__("os").environ, "PYTHONPATH": str(V2_ROOT / "src")},
    )
    log({"status": "downstream_done", "returncode": rc.returncode})
    return rc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
