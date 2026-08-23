"""Build grounded, safety-checked evidence rationales."""

from __future__ import annotations

import json

from pipeline_core.safety import assert_safe

from app.adapters.llm.factory import iter_llm_clients
from app.adapters.llm.ollama_client import SYSTEM_PROMPT
from app.models_orm import AnalysisRun
from app.schemas.rationale import GroundedRationaleResponse, RationaleClaim
from app.services.rationale_validator import claims_to_prose, validate_rationale


def _candidate(run: AnalysisRun, drug: str | None) -> dict | None:
    payload = run.result_payload or {}
    rows = (payload.get("overlap_nominations") or []) + (payload.get("overlap_exploratory") or [])
    rows += payload.get("clinical_comparators") or []
    if not drug:
        return rows[0] if rows else None
    return next((item for item in rows if str(item.get("drug", "")).lower() == drug.lower()), None)


def deterministic_rationale(run: AnalysisRun, drug: str | None = None) -> GroundedRationaleResponse:
    payload = run.result_payload or {}
    prediction = payload.get("cluster_prediction") or {}
    candidate = _candidate(run, drug)
    limitations = payload.get("limitations") or []
    supporting: list[RationaleClaim] = []
    counter: list[RationaleClaim] = []
    if prediction:
        supporting.append(
            RationaleClaim(
                text=(
                    f"The RNA-only surrogate places the largest probability on MOFA cluster "
                    f"{prediction.get('top_cluster')} "
                    f"({float(prediction.get('top_probability') or 0):.0%}, "
                    f"{prediction.get('confidence_level')} confidence)."
                ),
                kind="support",
                evidence_keys=["cluster_prediction.top_cluster", "cluster_prediction.top_probability"],
                section="mofa",
            )
        )
    if candidate:
        status = candidate.get("human_development_label") or candidate.get("indication_bucket") or "unclassified"
        supporting.append(
            RationaleClaim(
                text=(
                    f"{candidate.get('drug')} is a research nomination with List 1 percentile "
                    f"{candidate.get('list1_percentile')} and List 2 percentile "
                    f"{candidate.get('list2_percentile')} "
                    f"({status}). This is transcriptional reversal evidence, not a treatment choice."
                ),
                kind="support",
                evidence_keys=["overlap_nominations[0].list1_percentile", "overlap_nominations[0].drug"]
                if (payload.get("overlap_nominations") or [{}])[0].get("drug") == candidate.get("drug")
                else ["cluster_prediction.top_cluster"],
                section="drug",
            )
        )
        if candidate.get("display_action") in {"exploratory_only", "technical_excluded"}:
            counter.append(
                RationaleClaim(
                    text="This compound is not in the default human-use presentation lane.",
                    kind="counter",
                    evidence_keys=["display_gate_summary"]
                    if payload.get("display_gate_summary") is not None
                    else ["limitations"],
                    section="drug",
                )
            )
    uncertainty = [
        RationaleClaim(
            text=limitations[0] if limitations else "All scores are retrospective research signals, not clinical validation.",
            kind="uncertainty",
            evidence_keys=["limitations"],
            section="mofa",
        )
    ]
    summary = (
        f"This de-identified synthetic profile is a research demonstration. "
        f"Cluster {prediction.get('top_cluster')} is the top RNA-only assignment; "
        f"{(candidate or {}).get('drug') or 'no compound'} is shown only as evidence, not a recommendation."
    )
    rationale = GroundedRationaleResponse(
        summary=summary,
        supporting_claims=supporting,
        counter_claims=counter,
        uncertainty=uncertainty,
        used_llm=False,
        fallback_used=True,
        provider="none",
        model="deterministic",
    )
    assert_safe(claims_to_prose(rationale), "deterministic rationale")
    return rationale


def _prompt(run: AnalysisRun, question: str, drug: str | None) -> str:
    payload = run.result_payload or {}
    candidate = _candidate(run, drug)
    context = {
        "patient_metadata": run.patient_metadata or {},
        "cluster_prediction": payload.get("cluster_prediction"),
        "overlap_nominations": (payload.get("overlap_nominations") or [])[:8],
        "overlap_exploratory": (payload.get("overlap_exploratory") or [])[:5],
        "display_gate_summary": payload.get("display_gate_summary"),
        "compound_registry_version": payload.get("compound_registry_version"),
        "selected_drug": candidate,
        "limitations": payload.get("limitations") or [],
        "q5_pcr": payload.get("administered_regimen_pcr"),
    }
    schema = {
        "summary": "string, under 80 words, no treatment recommendation",
        "supporting_claims": [{"text": "string", "evidence_keys": ["path.to.field"], "citation_ids": [], "section": "drug"}],
        "counter_claims": [{"text": "string", "evidence_keys": ["limitations"], "section": "mofa"}],
        "uncertainty": [{"text": "string", "evidence_keys": ["limitations"], "section": "mofa"}],
    }
    return (
        "Return JSON only matching this schema: "
        f"{json.dumps(schema)}. Use only facts in the context. "
        "Every claim needs evidence_keys that exist in the context JSON. "
        "Do not recommend treatment, dose, or eligibility.\n\n"
        f"Context: {json.dumps(context, default=str)[:12000]}\n"
        f"Question: {question}"
    )


def build_rationale(run: AnalysisRun, question: str, drug: str | None = None) -> GroundedRationaleResponse:
    fallback = deterministic_rationale(run, drug)
    prompt = _prompt(run, question, drug)
    payload = run.result_payload or {}
    for client in iter_llm_clients():
        raw, used = client.generate_structured(prompt, SYSTEM_PROMPT)
        if not used or not raw:
            continue
        try:
            raw.setdefault("used_llm", True)
            raw.setdefault("fallback_used", False)
            raw.setdefault("provider", client.provider_name)
            raw.setdefault("model", client.model_name)
            validated = validate_rationale(raw, payload)
            validated.used_llm = True
            validated.fallback_used = False
            validated.provider = client.provider_name
            validated.model = client.model_name
            assert_safe(claims_to_prose(validated), "llm rationale")
            return validated
        except (ValueError, Exception):
            continue
    return fallback
