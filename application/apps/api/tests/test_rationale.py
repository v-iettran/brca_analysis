"""Grounded rationale schema, numeric/citation checks, and eval-set refusals."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline_core.safety import check_safety

from app.schemas.chat import CopilotChatRequest
from app.services.rationale_service import deterministic_rationale
from app.services.rationale_validator import validate_rationale
from app.services.copilot_service import answer_copilot_question

FIXTURES = Path(__file__).parent / "fixtures"


def _run_payload() -> dict:
    return {
        "cluster_prediction": {
            "top_cluster": 2,
            "top_probability": 0.82,
            "confidence_level": "high",
        },
        "overlap_nominations": [
            {
                "drug": "paclitaxel",
                "canonical": "paclitaxel",
                "list1_percentile": 0.91,
                "list2_percentile": 0.84,
                "human_development_label": "Approved drug (breast-cancer context)",
                "display_action": "default_visible",
                "literature_summary": {"top_citations": [{"pmid": "12345", "doi": "10.1/test"}]},
            }
        ],
        "display_gate_summary": {"n_default_visible": 1, "ranking_preserved": True},
        "limitations": [
            "Cluster signatures are one-vs-rest among METABRIC tumours; there is no normal-breast reference."
        ],
    }


def _run():
    payload = _run_payload()
    return SimpleNamespace(
        result_payload=payload,
        patient_metadata={"er_status": "Positive"},
        administered_regimen=["paclitaxel"],
        cluster_probabilities={"2": 0.82},
    )


def test_validate_rationale_rejects_unknown_keys_and_numbers():
    payload = _run_payload()
    with pytest.raises(ValueError, match="unknown evidence key"):
        validate_rationale(
            {
                "summary": "Research evidence only.",
                "supporting_claims": [
                    {"text": "Invented fact", "evidence_keys": ["not.a.field"], "kind": "support"}
                ],
            },
            payload,
        )
    with pytest.raises(ValueError, match="ungrounded numeric"):
        validate_rationale(
            {
                "summary": "Research evidence only.",
                "supporting_claims": [
                    {
                        "text": "Response rate is 99.9%",
                        "evidence_keys": ["limitations"],
                        "kind": "support",
                    }
                ],
            },
            payload,
        )


def test_validate_rationale_rejects_unsafe_language():
    payload = _run_payload()
    with pytest.raises(ValueError, match="unsafe"):
        validate_rationale(
            {
                "summary": "We recommend paclitaxel.",
                "supporting_claims": [
                    {"text": "Cluster 2 is assigned.", "evidence_keys": ["cluster_prediction.top_cluster"]}
                ],
            },
            payload,
        )


def test_deterministic_rationale_is_grounded_and_safe():
    rationale = deterministic_rationale(_run(), "paclitaxel")
    validated = validate_rationale(rationale.model_dump(), _run_payload())
    assert validated.fallback_used is True
    assert check_safety(validated.summary) == []


def test_eval_set_clinical_advice_is_refused():
    cases = json.loads((FIXTURES / "rationale_eval_set.json").read_text())["cases"]
    run = _run()
    for case in cases:
        request = CopilotChatRequest(message=case["question"], selected_drug=case.get("selected_drug"))
        response = answer_copilot_question(run, request)
        answer = response["answer"].lower()
        assert check_safety(response["answer"]) == []
        for banned in case["must_not_contain"]:
            assert banned.lower() not in answer
        if "what should i take" in case["question"].lower() or "dose" in case["question"].lower():
            assert "does not recommend treatment" in answer
        assert response["rationale"] is not None
        assert response["rationale"]["fallback_used"] is True


def test_v3_copilot_does_not_mention_mofa():
    run = _run()
    run.result_payload["v3_patient"] = {
        "modalities_used": ["rna", "cna", "methylation"],
        "position": {"cluster": {"label": 0, "posterior_mass": 1.0}},
        "nearest_lines": [{"line_id": "UACC893"}],
    }
    run.result_payload["v3_cohort"] = {
        "preregistered": {"k": 5},
        "gates": {"a2": {"framing": "descriptive"}},
    }
    request = CopilotChatRequest(message="Summarize this patient profile")
    response = answer_copilot_question(run, request)
    answer = response["answer"].lower()
    assert "mofa" not in answer
    assert "surrogate" not in answer
    assert "subgroup 1" in answer
    assert "rna + cna + methylation" in answer
    assert "evidence, not as recommendations" in answer
    assert check_safety(response["answer"]) == []
