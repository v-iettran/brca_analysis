"""Regimen-level pCR (pathological complete response) support, gated strictly.

Design decision (documented for clinicians and reviewers): the original Q5.R
pipeline validated two models on GSE20194/GSE25065 -- "Q2 regimen signature"
alone, and "Q2 regimen + Q4 METABRIC signature" (the *old* BRCA1/2-focused
signature, ``final-project/brca_target_pipeline.py``). That legacy Q4 feature
is a population-level BRCA signature, not a per-patient MOFA cluster score, so
mixing it into a live single-patient tool would be misleading.

This module instead:

1. Refits the Q2-only model in Python and checks it reproduces the committed
   R probabilities/AUROC (`q5_parity_report`) -- this is the portable,
   testable patient-scoring math the plan asks for.
2. Computes a genuinely new MOFA regimen-reversal feature from GCTX evidence
   for any patient we have full RNA for (our synthetic, METABRIC-derived demo
   patients) and reports it as a *separate, clearly-labeled* discovery signal.
3. Refuses to fuse the two into a single pCR probability for the external
   GSE cohorts, because that would require re-deriving per-patient MOFA
   cluster probabilities from raw GEO expression (GEOquery + platform
   annotation packages), which is not available in this environment. See
   ``jobs/refit_pcr_with_mofa.py`` and ``docs/mofa_copilot/LIMITATIONS.md``
   for the documented, honest "not yet validated" status of that combined
   model -- we do not hide this behind optimistic wording.
4. Only returns a pCR probability at all when the patient's regimen matches
   one of the two cohorts Q5.R actually validated, and only if that cohort's
   held-out AUROC clears ``PCR_APPLICABILITY_GATE_AUROC_MIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from pipeline_core.config import Q5_TABLES_DIR
from pipeline_core.gctx_evidence import blended_drug_evidence
from pipeline_core.q2_evidence import regimen_score as q2_regimen_score

PCR_APPLICABILITY_GATE_AUROC_MIN = 0.60

# Regimens Q5.R actually validated patient-level pCR against, normalized so
# either taxane (paclitaxel/docetaxel) counts as a match.
REPRESENTED_REGIMENS = {
    "GSE20194": {
        "label": "FAC/FEC + weekly taxane (5-fluorouracil, doxorubicin, taxane)",
        "base_drugs": ["5-fluorouracil", "doxorubicin"],
        "taxane_options": ["paclitaxel", "docetaxel"],
        "cohort": "GSE20194",
        "validation_split": "validation_100",
    },
    "GSE25065": {
        "label": "5-FU/anthracycline + taxane (5-fluorouracil, doxorubicin, taxane)",
        "base_drugs": ["5-fluorouracil", "doxorubicin"],
        "taxane_options": ["paclitaxel", "docetaxel"],
        "cohort": "GSE25065",
        "validation_split": "external_validation",
    },
}


@lru_cache(maxsize=1)
def load_predictions() -> pd.DataFrame:
    path = Q5_TABLES_DIR / "patient_external_validation_predictions.csv"
    if not path.exists():
        raise FileNotFoundError(f"Q5 patient predictions not found at {path}")
    return pd.read_csv(path)


@lru_cache(maxsize=1)
def load_committed_metrics() -> pd.DataFrame:
    path = Q5_TABLES_DIR / "patient_external_validation_metrics.csv"
    if not path.exists():
        raise FileNotFoundError(f"Q5 validation metrics not found at {path}")
    return pd.read_csv(path)


def fit_q2_only_pcr_model() -> sm.discrete.discrete_model.BinaryResultsWrapper:
    """Refit `pcr ~ q2_regimen_score` on the GSE20194 development_130 split,
    exactly as Q5.R's `glm(pcr ~ q2_regimen_score, family = binomial(...))`
    calibrated on the same split before scoring validation_100/GSE25065."""
    df = load_predictions()
    train = df[df["split"] == "development_130"].dropna(subset=["q2_regimen_score", "pcr"])
    X = sm.add_constant(train["q2_regimen_score"])
    return sm.Logit(train["pcr"], X).fit(disp=0)


def _binary_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    return {
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "negatives": int(len(y_true) - y_true.sum()),
        "auroc": float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) > 1 else None,
        "auprc": float(average_precision_score(y_true, y_prob)),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "log_loss": float(log_loss(y_true, y_prob, labels=[0, 1])),
    }


@dataclass
class ParityReport:
    """Compares our Python refit against the committed R model outputs."""

    probability_correlation: float
    max_absolute_difference: float
    python_metrics: dict[str, dict]
    committed_metrics: dict[str, dict]


def q5_parity_report() -> ParityReport:
    df = load_predictions().dropna(subset=["q2_regimen_score", "pcr"]).copy()
    model = fit_q2_only_pcr_model()
    X = sm.add_constant(df["q2_regimen_score"])
    df["python_probability_q2"] = model.predict(X)

    corr = float(np.corrcoef(df["python_probability_q2"], df["probability_q2"])[0, 1])
    max_abs_diff = float((df["python_probability_q2"] - df["probability_q2"]).abs().max())

    python_metrics, committed_metrics = {}, {}
    committed = load_committed_metrics()
    committed = committed[committed["model"] == "Q2 regimen signature"]

    for cohort, split in [("GSE20194", "validation_100"), ("GSE25065", "external_validation")]:
        subset = df[(df["accession"] == cohort) & (df["split"] == split)]
        python_metrics[f"{cohort}:{split}"] = _binary_metrics(
            subset["pcr"].to_numpy(), subset["python_probability_q2"].to_numpy()
        )
        row = committed[(committed["cohort"] == cohort) & (committed["split"] == split)]
        if not row.empty:
            committed_metrics[f"{cohort}:{split}"] = {
                "auroc": float(row["auroc"].iloc[0]),
                "auprc": float(row["auprc"].iloc[0]),
                "brier": float(row["brier"].iloc[0]),
                "log_loss": float(row["log_loss"].iloc[0]),
            }

    return ParityReport(
        probability_correlation=corr,
        max_absolute_difference=max_abs_diff,
        python_metrics=python_metrics,
        committed_metrics=committed_metrics,
    )


def _match_represented_regimen(regimen_drugs: list[str]) -> dict | None:
    normalized = {d.lower().strip() for d in regimen_drugs}
    for spec in REPRESENTED_REGIMENS.values():
        base_ok = all(d in normalized for d in spec["base_drugs"])
        taxane_ok = any(d in normalized for d in spec["taxane_options"])
        if base_ok and taxane_ok:
            return spec
    return None


def applicability_gate(regimen_drugs: list[str]) -> dict:
    """Return whether this regimen is represented in a validated cohort and,
    if so, whether that cohort's AUROC clears the display gate."""
    spec = _match_represented_regimen(regimen_drugs)
    if spec is None:
        return {
            "represented": False,
            "gate_passed": False,
            "reason": (
                "This regimen does not match a Q5-validated external cohort "
                "(GSE20194 or GSE25065). Any drug evidence shown for it is a "
                "discovery hypothesis, not a validated pCR estimate."
            ),
        }

    metrics = load_committed_metrics()
    row = metrics[
        (metrics["model"] == "Q2 regimen signature")
        & (metrics["cohort"] == spec["cohort"])
        & (metrics["split"] == spec["validation_split"])
    ]
    auroc = float(row["auroc"].iloc[0]) if not row.empty else None
    gate_passed = auroc is not None and auroc >= PCR_APPLICABILITY_GATE_AUROC_MIN
    return {
        "represented": True,
        "regimen_label": spec["label"],
        "validated_cohort": spec["cohort"],
        "validated_split": spec["validation_split"],
        "held_out_auroc": auroc,
        "gate_threshold": PCR_APPLICABILITY_GATE_AUROC_MIN,
        "gate_passed": gate_passed,
        "reason": (
            None
            if gate_passed
            else f"Held-out AUROC ({auroc:.2f}) is below the display gate "
            f"({PCR_APPLICABILITY_GATE_AUROC_MIN:.2f}); pCR is withheld even though "
            "the regimen matches a validated cohort."
        ),
    }


def calculate_supported_pcr(
    patient_expression: dict[str, float],
    regimen_drugs: list[str],
    cluster_probabilities: dict[int, float] | None = None,
) -> dict:
    """Only return a pCR probability for regimens Q5 actually validated and
    only if the applicability gate passes. Always also return the MOFA
    regimen-reversal signal as a *separate*, non-fused discovery component."""
    gate = applicability_gate(regimen_drugs)

    mofa_reversal = None
    if cluster_probabilities:
        percentiles = [
            blended_drug_evidence(cluster_probabilities, d)["blended_percentile"]
            for d in regimen_drugs
        ]
        percentiles = [p for p in percentiles if p is not None]
        if percentiles:
            mofa_reversal = float(np.mean(percentiles))

    result = {
        "applicability_gate": gate,
        "mofa_regimen_reversal_percentile": mofa_reversal,
        "mofa_regimen_reversal_note": (
            "Discovery-only signal: probability-weighted GCTX transcriptional "
            "reversal for the administered drugs, blended across this patient's "
            "MOFA cluster probabilities. Not fused into the pCR estimate below -- "
            "see docs/mofa_copilot/LIMITATIONS.md."
        ),
        "pcr_probability": None,
        "q2_regimen_score": None,
    }

    if not gate["gate_passed"]:
        return result

    q2_result = q2_regimen_score(patient_expression, regimen_drugs)
    result["q2_regimen_score"] = q2_result
    if q2_result.get("regimen_score") is None:
        result["applicability_gate"]["reason"] = (
            "Regimen is represented and the cohort gate passed, but this patient's "
            "own expression data could not be scored for any regimen drug "
            "(insufficient gene coverage)."
        )
        return result

    model = fit_q2_only_pcr_model()
    X = pd.DataFrame({"const": [1.0], "q2_regimen_score": [q2_result["regimen_score"]]})
    X = X[model.params.index]
    result["pcr_probability"] = float(model.predict(X)[0])
    return result
