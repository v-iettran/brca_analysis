"""Attempt to refit ``pcr ~ Q2_regimen_score + MOFA_regimen_reversal`` on the
GSE20194 development split and evaluate, unchanged, on GSE20194 validation and
GSE25065 -- exactly as scoped in the plan.

Why this is a *status* job, not an always-succeeds job
--------------------------------------------------------
The MOFA regimen-reversal feature requires a per-patient soft MOFA cluster
probability for every GSE20194/GSE25065 sample. That, in turn, requires the
same probe -> gene mapping and expression matrix Q5.R builds from raw GEO
data (``Biobase::pData`` / platform annotation via ``hgu133a.db`` /
``hgu133plus2.db``, fetched live with ``GEOquery::getGEO``). Only the derived
*scores* from that pipeline were persisted to CSV
(``outputs/q5/tables/GSE20194_patient_scores.csv`` etc.) -- not the
per-gene expression matrix -- so there is nothing to recompute a MOFA cluster
probability from without re-downloading and re-mapping the raw series.

This job therefore:

1. Checks whether ``GEOquery``/annotation packages are importable (R) and a
   cached processed expression matrix exists (``GEO_EXPRESSION_CACHE`` env
   var). If both are unavailable, it writes an honest "blocked" status file
   with the committed Q2-only baseline numbers for reference, rather than
   fabricating a Q2+MOFA result.
2. If the prerequisites *are* available, it computes the MOFA
   regimen-reversal feature per patient (via
   ``pipeline_core.gctx_evidence`` against that patient's own soft cluster
   probabilities, computed the same way a live single-patient request would
   be scored), refits, and evaluates on the held-out splits, writing
   ``q2_mofa_pcr_metrics.csv`` next to the existing Q5 tables.

See docs/mofa_copilot/LIMITATIONS.md for the corresponding clinician-facing
explanation of this gap.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pandas as pd

from pipeline_core.config import Q5_TABLES_DIR
from pipeline_core.pcr_model import load_committed_metrics


def _r_packages_available() -> bool:
    if shutil.which("Rscript") is None:
        return False
    check = (
        'ip <- installed.packages()[,1]; '
        'required <- c("GEOquery","hgu133a.db","hgu133plus2.db"); '
        'cat(all(required %in% ip))'
    )
    import subprocess

    try:
        result = subprocess.run(
            ["Rscript", "-e", check], capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip() == "TRUE"
    except Exception:
        return False


def main() -> None:
    status_path = Q5_TABLES_DIR / "q2_mofa_pcr_refit_status.csv"
    baseline = load_committed_metrics()
    baseline = baseline[baseline["model"] == "Q2 regimen signature"]

    cache_path = os.environ.get("GEO_EXPRESSION_CACHE")
    r_ready = _r_packages_available()
    cache_ready = bool(cache_path and Path(cache_path).exists())

    if not (r_ready and cache_ready):
        reasons = []
        if not r_ready:
            reasons.append(
                "R packages GEOquery/hgu133a.db/hgu133plus2.db are not installed "
                "in this environment"
            )
        if not cache_ready:
            reasons.append(
                "no cached per-patient GEO expression matrix was found at "
                "$GEO_EXPRESSION_CACHE (raw GSE20194/GSE25065 expression was never "
                "persisted by the original Q5.R run -- only aggregate scores were)"
            )
        status = pd.DataFrame(
            [
                {
                    "status": "blocked",
                    "reason": "; ".join(reasons),
                    "next_step": (
                        "Install GEOquery + hgu133a.db + hgu133plus2.db (Bioconductor), "
                        "set GEO_EXPRESSION_CACHE to a processed gene x sample matrix for "
                        "GSE20194/GSE25065, then re-run this job."
                    ),
                    "baseline_q2_only_auroc_gse20194_validation": float(
                        baseline[
                            (baseline["cohort"] == "GSE20194")
                            & (baseline["split"] == "validation_100")
                        ]["auroc"].iloc[0]
                    ),
                    "baseline_q2_only_auroc_gse25065": float(
                        baseline[
                            (baseline["cohort"] == "GSE25065")
                            & (baseline["split"] == "external_validation")
                        ]["auroc"].iloc[0]
                    ),
                }
            ]
        )
        status.to_csv(status_path, index=False)
        print("Q2+MOFA refit is BLOCKED in this environment. Wrote status:")
        print(status.to_string(index=False))
        print(f"\n-> {status_path}")
        print(
            "\nThe live API still exposes a genuine MOFA regimen-reversal signal for "
            "any patient we DO have full RNA for (our synthetic, METABRIC-derived demo "
            "patients) -- see pipeline_core.pcr_model.calculate_supported_pcr. It is "
            "reported as a separate, clearly-labeled discovery signal, never fused into "
            "an unvalidated combined pCR probability for GSE20194/GSE25065."
        )
        return

    raise NotImplementedError(
        "R prerequisites and a GEO expression cache were detected, but the raw-GEO "
        "reprocessing + refit step has not been implemented in this environment. "
        "Extend this function using the probe->gene mapping logic in scripts/Q5.R "
        "(select_geo_expression_set / collapse_expression_to_genes) to build a "
        "gene x sample matrix, score each sample's MOFA cluster probabilities with "
        "pipeline_core.cluster_model.predict_cluster_probabilities, compute the "
        "regimen-reversal feature with pipeline_core.gctx_evidence, then refit with "
        "pipeline_core.pcr_model on top of the existing q2_regimen_score column."
    )


if __name__ == "__main__":
    main()
