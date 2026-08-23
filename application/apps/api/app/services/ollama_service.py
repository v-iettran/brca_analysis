"""Plain-language explanation helper, backed by the local Ollama model with a
deterministic template fallback so the API works even with Ollama disabled,
unreachable, or unpulled."""

from __future__ import annotations

from pipeline_core.cluster_model import ClusterPrediction

from app.adapters.ollama_client import generate_explanation
from app.config import get_settings

settings = get_settings()


def _cluster_fallback(prediction: ClusterPrediction) -> str:
    top_pct = f"{prediction.top_probability:.0%}"
    return (
        f"The RNA-only surrogate model assigns this profile to MOFA cluster "
        f"{prediction.top_cluster} with {top_pct} probability "
        f"({prediction.confidence_level} confidence), based on "
        f"{prediction.genes_found}/{prediction.genes_requested} reference genes "
        f"({prediction.gene_coverage:.0%} coverage). This is a soft, "
        f"probabilistic cluster assignment derived from RNA alone, not a "
        f"diagnosis or subtype label."
    )


def explain_cluster_prediction(prediction: ClusterPrediction) -> tuple[str, bool]:
    fallback = _cluster_fallback(prediction)
    if not settings.ollama_enabled:
        return fallback, False

    probs_text = ", ".join(f"cluster {c}: {p:.1%}" for c, p in sorted(prediction.probabilities.items()))
    prompt = (
        f"A patient's RNA profile was scored against 5 MOFA multi-omics clusters "
        f"derived from METABRIC. Cluster probabilities: {probs_text}. Gene coverage: "
        f"{prediction.gene_coverage:.0%} ({prediction.genes_found}/{prediction.genes_requested} genes). "
        f"Confidence level: {prediction.confidence_level}. In 2-3 sentences, explain this result to a "
        f"clinician in plain language. Do not recommend a treatment or claim diagnostic certainty."
    )
    return generate_explanation(settings.ollama_host, settings.ollama_model, prompt, fallback=fallback)


def explain_drug_evidence(drug: str, gctx_percentile: float | None, q2_evidence: dict | None) -> tuple[str, bool]:
    parts = [f"Evidence summary for {drug}:"]
    if gctx_percentile is not None:
        parts.append(f"GCTX transcriptional reversal percentile {gctx_percentile:.0%}.")
    if q2_evidence and q2_evidence.get("evidence_category"):
        parts.append(f"Q2 cell-line evidence category: {q2_evidence['evidence_category']}.")
    fallback = " ".join(parts) if len(parts) > 1 else f"No evidence components were available for {drug}."

    if not settings.ollama_enabled:
        return fallback, False

    prompt = (
        f"Explain this cancer drug evidence in plain language for a clinician, in 2 sentences, "
        f"without recommending treatment or claiming eligibility: drug={drug}, "
        f"gctx_reversal_percentile={gctx_percentile}, q2_evidence={q2_evidence}."
    )
    return generate_explanation(settings.ollama_host, settings.ollama_model, prompt, fallback=fallback)
