"""Run-aware, safety-constrained local research copilot.

The copilot only phrases evidence already present in an immutable analysis
run. It does not calculate scientific values, query patient expression, make
eligibility decisions, or select a therapy.
"""

from __future__ import annotations

import json

from pipeline_core.safety import assert_safe, check_safety

from app.adapters.llm.factory import iter_llm_clients
from app.adapters.llm.ollama_client import SYSTEM_PROMPT
from app.models_orm import AnalysisRun
from app.schemas.chat import CopilotChatRequest
from app.services.cluster_service import cluster_detail
from app.services.rationale_service import build_rationale


def _candidate_for(run: AnalysisRun, drug: str | None) -> dict | None:
    if not drug:
        return None
    payload = run.result_payload or {}
    candidates = payload.get("overlap_nominations") or payload.get("top_candidate_drugs") or []
    return next((item for item in candidates if item["drug"].lower() == drug.lower()), None)


def _cluster_context(run: AnalysisRun, requested_cluster: int | None) -> dict | None:
    payload = run.result_payload or {}
    if payload.get("v3_patient"):
        return None
    prediction = payload.get("cluster_prediction") or {}
    cluster_id = requested_cluster
    if cluster_id is None:
        cluster_id = prediction.get("top_cluster")
    probabilities = run.cluster_probabilities or {}
    if cluster_id is None or str(cluster_id) not in probabilities:
        return None
    try:
        return cluster_detail(cluster_id, float(probabilities[str(cluster_id)]), top_n=8)
    except (FileNotFoundError, ValueError, KeyError):
        return None


def _v3_summary(payload: dict) -> str | None:
    patient = payload.get("v3_patient") or {}
    if not patient:
        return None
    cohort = payload.get("v3_cohort") or {}
    modalities = patient.get("modalities_used") or patient.get("modalities_present") or []
    modality_text = " + ".join(modalities) if modalities else "available assays"
    pos = (patient.get("position") or {}).get("cluster") or {}
    label = int(pos.get("label") or 0) + 1
    mass = float(pos.get("posterior_mass") or 0)
    k = (cohort.get("preregistered") or {}).get("k")
    a2 = (cohort.get("gates") or {}).get("a2") or {}
    lines = patient.get("nearest_lines") or []
    parts = [
        f"This held-out TCGA profile is encoded from {modality_text}.",
        f"It has {mass:.0%} membership in subgroup {label}" + (f" of {k}." if k else "."),
        "Subgroups are chosen from molecular structure, never from survival.",
    ]
    if a2.get("framing") == "descriptive":
        parts.append("They did not separate survival in this cohort, so the overlay is descriptive.")
    if lines:
        parts.append(
            f"{len(lines)} measured cell lines resemble this tumour. "
            "Compounds are shown as evidence, not as recommendations."
        )
    return " ".join(parts)


def _sources(request: CopilotChatRequest, candidate: dict | None) -> list[dict]:
    question = request.message.lower()
    sources = [{"label": "De-identified patient profile", "section": "patient"}]
    if request.active_view == "clinical_trials" or any(term in question for term in ("trial", "eligib")):
        sources.append({"label": "Clinical trial explorer", "section": "trial"})
    if any(term in question for term in ("cluster", "subgroup", "mofa", "gene", "rna", "signature", "residual")):
        sources.append({"label": "Structure-selected subgroup panels", "section": "mofa"})
    if any(term in question for term in ("q5", "pcr", "regimen", "response", "almanac")):
        sources.append({"label": "Q5 / ALMANAC preclinical evidence", "section": "q5"})
    if any(term in question for term in ("predictor", "q2 reliability", "q4 support", "comparator")):
        sources.append(
            {
                "label": "Parallel Predictor clinical-comparator context",
                "section": "drug",
            }
        )
    if (
        candidate
        and candidate["drug"].lower() in question
        or any(term in question for term in ("drug", "gctx", "q2", "target", "overlap", "nominat"))
    ):
        sources.append(
            {
                "label": f"Overlap nomination for {candidate['drug']}" if candidate else "Overlap nominations",
                "section": "drug",
            }
        )
    if any(term in question for term in ("literature", "paper", "citation")):
        sources.append({"label": "Paperclip literature retrieval", "section": "literature"})
    return sources


def _fallback_answer(
    run: AnalysisRun,
    request: CopilotChatRequest,
    candidate: dict | None,
    selected_cluster: dict | None,
) -> str:
    payload = run.result_payload or {}
    prediction = payload.get("cluster_prediction") or {}
    pcr = payload.get("administered_regimen_pcr") or {}
    gate = pcr.get("applicability_gate") or {}
    question = request.message.lower()
    overlap = payload.get("overlap_nominations") or []
    if any(
        term in question
        for term in (
            "what should i take",
            "what should i use",
            "which drug should",
            "should i take",
            "prescribe",
            "dosage",
            "what dose",
            "best treatment",
            "recommend treatment",
        )
    ):
        return (
            "This tool does not recommend treatment, dose, or a drug to take. "
            "It only summarizes already-computed research evidence. A qualified clinician "
            "must interpret these signals independently."
        )
    comparator = next(
        (
            row
            for row in payload.get("clinical_comparators") or []
            if str(row.get("drug", "")).lower() in question
        ),
        None,
    )

    if request.active_view == "clinical_trials" or any(term in question for term in ("trial", "eligib")):
        return (
            "Open Clinical Trials to review recruiting studies linked to overlap nominations. "
            "Each criterion is labeled met, not met, or unknown from the public eligibility text. "
            "A potential match means no known exclusion was found; it is not an enrollment decision."
        )

    if any(
        term in question
        for term in ("predictor", "q2 reliability", "q4 support", "clinical comparator")
    ):
        predictor = (comparator or {}).get("predictor_evidence") or {}
        if comparator and predictor:
            return (
                f"{comparator['drug']} has reference-cohort Q2 sensitivity "
                f"{float(predictor.get('reference_cohort_sensitivity_percentile') or 0):.0%}, "
                f"Q2 model reliability {float(predictor.get('q2_model_reliability') or 0):.0%}, "
                f"and Q4 support {float(predictor.get('q4_drug_support') or 0):.0%}. "
                f"Its integrated Predictor priority is "
                f"{float(predictor.get('integrated_single_drug_priority') or 0):.3f}; "
                f"concordance is {str(comparator.get('evidence_concordance') or 'unknown').replace('_', ' ')}. "
                "This parallel context does not alter List 1/List 2 nomination rank."
            )
        predictor_combos = payload.get("predictor_combinations") or []
        if predictor_combos and any(
            term in question for term in ("combination", "pair", "almanac")
        ):
            top = predictor_combos[0]
            return (
                f"The highest Predictor comparator pair is {top.get('combination')} "
                f"(priority {float(top.get('integrated_combination_priority') or 0):.3f}). "
                "It combines component-drug context, aligned ALMANAC support, and pair Q4 support. "
                "This is a preclinical comparator lane, not an overlap nomination."
            )
        return (
            "Predictor context combines reference-cohort Q2 sensitivity (60%), Q2 model "
            "reliability (25%), and Q4 support (15%). It is displayed separately from "
            "List 1/List 2 so correlated Q4 evidence is not counted twice."
        )

    if any(term in question for term in ("q5", "pcr", "regimen", "response", "almanac")):
        combos = payload.get("almanac_combinations") or []
        parts = []
        if combos:
            top = combos[0]
            parts.append(
                f"Top ALMANAC-aligned combination in this run is {top.get('combination')} "
                f"(preclinical priority only; not a dose or response probability)."
            )
        if pcr.get("pcr_probability") is not None:
            parts.append(
                f"Separately, the historical Q5 pCR estimate for the administered regimen is "
                f"{pcr['pcr_probability']:.0%} on {gate.get('validated_cohort')}."
            )
        elif gate:
            parts.append(gate.get("reason") or "No calibrated pCR estimate is displayed for this regimen.")
        return " ".join(parts) if parts else "No Q5/ALMANAC combination evidence is available for this run."

    if candidate and (
        candidate["drug"].lower() in question
        or any(term in question for term in ("drug", "gctx", "q2", "target", "why did", "nominat", "overlap"))
    ):
        tier = candidate.get("evidence_tier") or "unspecified"
        indication = candidate.get("indication_bucket") or "unclassified"
        parts = [
            f"{candidate['drug']} is an overlap nomination (List 1 cluster reversal ∩ List 2 residual reversal).",
            f"List 1 percentile {candidate.get('list1_percentile', candidate.get('gctx_evidence', {}).get('blended_percentile'))}, "
            f"List 2 percentile {candidate.get('list2_percentile')}.",
            f"Evidence tier: {tier.replace('_', ' ')}; indication bucket: {indication.replace('_', ' ')}.",
        ]
        q2 = candidate.get("q2_annotation") or candidate.get("q2_evidence")
        if q2 and q2.get("sensitivity_percentile") is not None:
            parts.append(
                f"Q2 sensitivity annotation percentile is {float(q2['sensitivity_percentile']):.0%} "
                "(annotation only; not used for nomination)."
            )
        elif q2 and q2.get("evidence_category"):
            parts.append(
                f"Q2 evidence category: {str(q2.get('evidence_category')).replace('_', ' ')} (annotation only)."
            )
        robustness = candidate.get("robustness") or {}
        if robustness.get("likely_artifact"):
            parts.append("Robustness checks flagged this hit as a possible artifact pending literature review.")
        if indication in {"repurposing_hypothesis", "unclassified_or_investigational"}:
            parts.append(
                "This compound is not a standard breast-cancer indication in the committed "
                "human-development registry; treat it as a literature-backed research hypothesis, "
                "not a treatment recommendation."
            )
        return " ".join(parts)

    v3_text = _v3_summary(payload)
    if v3_text:
        return v3_text

    if selected_cluster and any(
        term in question for term in ("cluster", "subgroup", "mofa", "gene", "coefficient", "rna", "signature", "residual")
    ):
        residual = payload.get("residual_signature") or {}
        higher = ", ".join(gene["gene"] for gene in selected_cluster["positive_genes"][:5])
        lower = ", ".join(gene["gene"] for gene in selected_cluster["negative_genes"][:5])
        return (
            f"Subgroup {selected_cluster['cluster_id']} has "
            f"{selected_cluster['patient_probability']:.0%} membership for this profile. "
            f"Cluster signature higher-expression genes include {higher}; lower-expression genes include {lower}. "
            f"The residual signature uses {residual.get('n_up', 0)} up / {residual.get('n_down', 0)} down genes "
            "(patient z minus cluster centroid). These are one-vs-rest / residual contrasts, not causal effects."
        )

    top_cluster = prediction.get("top_cluster")
    top_probability = prediction.get("top_probability")
    probability_text = (
        f"{float(top_probability):.0%}" if top_probability is not None else "an unavailable probability"
    )
    metadata = run.patient_metadata or {}
    receptor_summary = ", ".join(
        part
        for part in (
            f"ER {metadata.get('er_status')}" if metadata.get("er_status") else "",
            f"PR {metadata.get('pr_status')}" if metadata.get("pr_status") else "",
            f"HER2 {metadata.get('her2_status')}" if metadata.get("her2_status") else "",
        )
        if part
    )
    return (
        f"This de-identified profile is {receptor_summary or 'missing receptor metadata'}. "
        f"The RNA model places the largest probability on subgroup {top_cluster} "
        f"({probability_text}), with {prediction.get('confidence_level', 'unknown')} confidence. "
        f"There are {len(overlap)} dual-list overlap nominations in this revision. "
        "Ask about a specific drug, signature, ALMANAC combination, or trial criterion for cited detail."
    )


def answer_copilot_question(run: AnalysisRun, request: CopilotChatRequest) -> dict:
    candidate = _candidate_for(run, request.selected_drug)
    selected_cluster = _cluster_context(run, request.selected_cluster)
    fallback = _fallback_answer(run, request, candidate, selected_cluster)
    assert_safe(fallback, "copilot deterministic fallback")
    rationale = build_rationale(run, request.message, request.selected_drug)

    answer, used_model = fallback, False
    provider, model = rationale.provider, rationale.model
    payload = run.result_payload or {}
    context = {
        "active_view": request.active_view,
        "patient_metadata": run.patient_metadata or {},
        "administered_regimen": run.administered_regimen,
        "cluster_prediction": payload.get("cluster_prediction"),
        "v3_patient": payload.get("v3_patient"),
        "v3_cohort_gates": (payload.get("v3_cohort") or {}).get("gates"),
        "selected_cluster_signature": selected_cluster,
        "overlap_nominations": (payload.get("overlap_nominations") or [])[:8],
        "human_development": [
            {
                "drug": row.get("drug"),
                "human_development_status": row.get("human_development_status"),
                "display_action": row.get("display_action"),
            }
            for row in (payload.get("overlap_nominations") or [])[:8]
        ],
        "selected_drug_evidence": candidate,
        "limitations": payload.get("limitations") or [],
    }
    history = [{"role": item.role, "content": item.content[:500]} for item in request.history[-6:]]
    prompt = (
        "Answer the clinician's research-evidence question using only the JSON context below. "
        "Do not infer missing facts, calculate new values, rank therapies, invent dosages, "
        "or declare clinical eligibility. Keep the answer under 160 words.\n\n"
        f"Context: {json.dumps(context, default=str)[:14000]}\n"
        f"Recent conversation: {json.dumps(history)}\n"
        f"Question: {request.message}"
    )
    for client in iter_llm_clients():
        text, used = client.generate_text(prompt, SYSTEM_PROMPT, fallback=fallback)
        if used and not check_safety(text):
            answer, used_model = text, True
            provider, model = client.provider_name, client.model_name
            break

    return {
        "answer": answer,
        "used_local_model": used_model and provider == "ollama",
        "sources": _sources(request, candidate),
        "rationale": rationale.model_dump(),
        "provider": provider,
        "model": model,
    }
