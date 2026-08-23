"""The named, deterministic "tools" the agent/API layer is built from.

Every tool here is a plain, testable Python function with no hidden state.
The optional local Ollama model (``services/ollama_service.py``) may
orchestrate *which* of these to call and may phrase their output in prose,
but it never computes a number itself and every prose response is
safety-checked before being shown.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline_core.cluster_model import ClusterPrediction, predict_cluster_probabilities
from pipeline_core.gctx_evidence import top_candidate_drugs
from pipeline_core.pcr_model import calculate_supported_pcr as _calculate_supported_pcr
from pipeline_core.q2_evidence import score_patient_all_drugs

from app.schemas.patient import PatientProfileIn


@dataclass
class ValidationResult:
    ok: bool
    warnings: list[str]
    gene_count: int
    unrecognized_regimen_drugs: list[str]


KNOWN_Q2_DRUGS = {
    "5-fluorouracil",
    "cisplatin",
    "docetaxel",
    "doxorubicin",
    "epirubicin",
    "gemcitabine",
    "paclitaxel",
}


def validate_patient(profile: PatientProfileIn) -> ValidationResult:
    warnings: list[str] = []
    gene_count = len(profile.expression)

    if gene_count < 200:
        warnings.append(
            f"Only {gene_count} genes were submitted; this is far below a typical "
            "expression array/RNA-seq panel and will likely trigger abstention."
        )

    unrecognized = sorted(
        {d for d in profile.administered_regimen if d not in KNOWN_Q2_DRUGS}
    )
    if unrecognized:
        warnings.append(
            f"These administered drugs have no Q2 signature model and will only "
            f"appear as discovery-evidence (GCTX) candidates, never a pCR estimate: "
            f"{', '.join(unrecognized)}."
        )

    return ValidationResult(
        ok=gene_count > 0,
        warnings=warnings,
        gene_count=gene_count,
        unrecognized_regimen_drugs=unrecognized,
    )


def score_clusters(expression: dict[str, float]) -> ClusterPrediction:
    return predict_cluster_probabilities(expression)


def score_q2_drugs(expression: dict[str, float]):
    return score_patient_all_drugs(expression)


def lookup_gctx_drugs(cluster_probabilities: dict[int, float], top_n: int = 15):
    return top_candidate_drugs(cluster_probabilities, top_n=top_n)


def calculate_supported_pcr(
    expression: dict[str, float],
    regimen_drugs: list[str],
    cluster_probabilities: dict[int, float] | None = None,
) -> dict:
    return _calculate_supported_pcr(expression, regimen_drugs, cluster_probabilities)
