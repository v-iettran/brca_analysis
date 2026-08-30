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
from app.services.copilot_guard import review_answer
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



def _v3_context(payload: dict) -> dict | None:
    """The evidence a conclusion about this case would actually rest on.

    The previous context was a two-sentence summary plus the gate block, which
    is not enough to say anything specific: no subgroup profile, no evidence
    tiers, no indication of which curves were measured rather than extrapolated.
    Everything here is copied from the payload verbatim so the grounding gate
    can trace any number the model repeats.
    """
    patient = payload.get("v3_patient") or {}
    cohort = payload.get("v3_cohort") or {}
    if not patient or not cohort:
        return None

    position = (patient.get("position") or {}).get("cluster") or {}
    cluster = int(position.get("label") or 0)
    annotation = (cohort.get("cluster_annotations") or {}).get(str(cluster)) or {}

    def top(family: str, limit: int) -> list[dict]:
        rows = [
            r
            for r in (cohort.get("cluster_profiles") or [])
            if r.get("family") == family
            and int(r.get("cluster", -1)) == cluster
            and float(r.get("q") or 1) < 0.05
        ]
        rows.sort(key=lambda r: abs(float(r.get("effect") or 0)), reverse=True)
        return [
            {
                "feature": r.get("feature"),
                "effect": round(float(r.get("effect") or 0), 3),
                "q": float(r.get("q") or 1),
                "direction": "raised" if float(r.get("effect") or 0) > 0 else "reduced",
                "evidence": r.get("evidence_tier"),
            }
            for r in rows[:limit]
        ]

    lines = []
    for line in (patient.get("nearest_lines") or [])[:5]:
        lines.append(
            {
                "name": line.get("name"),
                "similarity": line.get("similarity"),
                "pam50": line.get("pam50"),
                "pam50_matches_patient": line.get("pam50_match"),
                "receptor_status": line.get("subtype_features"),
                "curves": [
                    {
                        "drug": c.get("canonical") or c.get("drug"),
                        "ic50_nm": c.get("ic50_nm"),
                        "max_tested_nm": c.get("max_conc_nm"),
                        "ic50_beyond_tested_range": c.get("ic50_extrapolated"),
                        "development_status": c.get("evidence_label"),
                    }
                    for c in (line.get("curves") or [])
                ],
            }
        )

    members = ((patient.get("reversal_candidates") or {}) or {}).get("members") or []
    by_tier: dict[str, list[str]] = {}
    for member in members:
        by_tier.setdefault(str(member.get("evidence_label") or "Not classified"), []).append(
            str(member.get("canonical") or member.get("drug"))
        )

    return {
        "patient": {
            "id": patient.get("patient_id"),
            "state": patient.get("state"),
            "assays_used": patient.get("modalities_used") or patient.get("modalities_present"),
            "pam50": patient.get("pam50"),
            "tumour_fraction": (patient.get("sample_quality") or {}).get("tumour_fraction"),
            "sample_verdict": (patient.get("sample_quality") or {}).get("verdict"),
            "abstained": (patient.get("abstention") or {}).get("abstained"),
            "abstention_reason": (patient.get("abstention") or {}).get("reason_text"),
        },
        "subgroup": {
            "number_shown_to_user": cluster + 1,
            "membership_probability": position.get("posterior_mass"),
            "size": annotation.get("n"),
            "pam50_majority": annotation.get("pam50_majority"),
            "defining_pathways": top("pathway", 6),
            "defining_transcription_factors": top("tf", 5),
            "defining_genes": top("gene", 8),
        },
        "cohort": {
            "n_samples": cohort.get("n_samples"),
            "source": cohort.get("cohort_source"),
            "preregistered_k": (cohort.get("preregistered") or {}).get("k"),
            "selection_rule": (cohort.get("preregistered") or {}).get("selection_rule"),
            "encoder_note": (cohort.get("provenance") or {}).get("encoder_note"),
        },
        "gates": cohort.get("gates"),
        "nearest_cell_lines": lines,
        "reversal_candidates_by_status": {k: v[:8] for k, v in by_tier.items()},
        "reversal_candidate_counts": {k: len(v) for k, v in by_tier.items()},
        "limitations": patient.get("limitations") or [],
    }


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
    context = _v3_context(payload) or {
        "active_view": request.active_view,
        "patient_metadata": run.patient_metadata or {},
        "administered_regimen": run.administered_regimen,
        "cluster_prediction": payload.get("cluster_prediction"),
        "selected_cluster_signature": selected_cluster,
        "overlap_nominations": (payload.get("overlap_nominations") or [])[:8],
        "selected_drug_evidence": candidate,
        "limitations": payload.get("limitations") or [],
    }
    context["active_view"] = request.active_view
    context["selected_drug_evidence"] = candidate

    history = [{"role": item.role, "content": item.content[:500]} for item in request.history[-6:]]
    prompt = (
        "You are describing a completed analysis to a clinical researcher.\n\n"
        "You may connect the panels into a conclusion about THE ANALYSIS: which subgroup this "
        "tumour falls in, what defines that subgroup, what was retrieved, and what the gates say. "
        "You may not draw a conclusion about the patient's care.\n\n"
        "Hard rules:\n"
        "- Every number you write must appear verbatim in the context. Never compute, round, or "
        "estimate a new one. If a number is not there, describe it in words instead.\n"
        "- Never name a drug that is not in the context.\n"
        "- Never recommend, rank, or call anything best, first-line, or eligible.\n"
        "- Where the analysis is uncertain or a gate failed, say so plainly rather than smoothing it.\n"
        "- Under 170 words. No preamble.\n"
        "- Write plain sentences. No markdown, no headings, no bold, no bullet characters.\n\n"
        f"Context: {json.dumps(context, default=str)[:16000]}\n"
        f"Recent conversation: {json.dumps(history)}\n"
        f"Question: {request.message}"
    )

    # The model is untrusted input: its answer is reviewed against the payload
    # and shown only if every number and named drug can be traced back to it.
    withheld: dict | None = None
    for client in iter_llm_clients():
        # Ask for the raw answer so this gate — not the client — decides, and
        # can tell the reader which check failed.
        if hasattr(client, "generate_reviewable"):
            text, used = client.generate_reviewable(prompt, SYSTEM_PROMPT)
        else:
            text, used = client.generate_text(prompt, SYSTEM_PROMPT, fallback=fallback)
        if not used or not str(text).strip():
            continue
        verdict = review_answer(text, context)
        if verdict["accepted"]:
            answer, used_model = text, True
            provider, model = client.provider_name, client.model_name
            withheld = None
            break
        withheld = {
            "reasons": verdict["reasons"],
            "unsupported_numbers": verdict["unsupported_numbers"],
            "unsupported_drugs": verdict["unsupported_drugs"],
            "banned_phrases": verdict["banned_phrases"],
        }

    # Keep a verbose answer replayable: ChatHistoryMessage caps content at 2000,
    # so an over-long reply would 422 every subsequent turn. Trim on a sentence
    # boundary rather than mid-clause, since the tail usually carries a caveat.
    if len(answer) > 1900:
        cut = answer.rfind(". ", 0, 1900)
        answer = (answer[: cut + 1] if cut > 800 else answer[:1900]).rstrip()

    return {
        "answer": answer,
        "used_local_model": used_model and provider == "ollama",
        "answer_source": "model" if used_model else "deterministic",
        "withheld": withheld,
        "sources": _sources(request, candidate),
        "rationale": rationale.model_dump(),
        "provider": provider,
        "model": model,
    }
