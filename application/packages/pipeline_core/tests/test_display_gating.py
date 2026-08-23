"""Display gating never mutates ranks or percentiles."""

from __future__ import annotations

from pipeline_core.display_gating import annotate_human_development, apply_display_gating


def _row(**overrides):
    base = {
        "drug": "paclitaxel",
        "canonical": "paclitaxel",
        "list1_rank": 12,
        "list2_rank": 8,
        "list1_percentile": 0.91,
        "list2_percentile": 0.84,
        "weaker_percentile": 0.84,
        "robustness": {},
    }
    base.update(overrides)
    return base


def test_gating_preserves_rank_fields(monkeypatch):
    monkeypatch.setattr(
        "pipeline_core.display_gating.lookup_compound",
        lambda **kwargs: {
            "human_development_status": "approved_breast",
            "entity_type": "approved_drug",
            "display_action": "default_visible",
            "display_gate_reason": "approved_human_use",
            "match_key": "canonical",
            "breast_oncology_relevance": "approved_breast",
            "withdrawn_or_discontinued": False,
            "sources": [],
        },
    )
    original = _row()
    gated = apply_display_gating([original])
    visible = gated["visible"][0]
    assert visible["list1_rank"] == 12
    assert visible["list2_rank"] == 8
    assert visible["list1_percentile"] == 0.91
    assert visible["list2_percentile"] == 0.84
    assert gated["gate_summary"]["ranking_preserved"] is True
    assert original["list1_rank"] == 12


def test_anonymous_and_unresolved_are_technically_excluded():
    anonymous = apply_display_gating([_row(drug="BRD-K000", canonical="brd-k000")])
    assert anonymous["technical_excluded"][0]["display_action"] == "technical_excluded"
    assert anonymous["technical_excluded"][0]["list1_rank"] == 12

    unresolved = apply_display_gating([_row(drug="unknownium", canonical="unknownium")])
    assert unresolved["technical_excluded"][0]["human_development_status"] == "unresolved"


def test_likely_artifact_overrides_default_lane(monkeypatch):
    monkeypatch.setattr(
        "pipeline_core.display_gating.lookup_compound",
        lambda **kwargs: {
            "human_development_status": "approved_breast",
            "entity_type": "approved_drug",
            "display_action": "default_visible",
            "display_gate_reason": "approved_human_use",
            "match_key": "canonical",
            "breast_oncology_relevance": "approved_breast",
            "withdrawn_or_discontinued": False,
            "sources": [],
        },
    )
    gated = apply_display_gating([_row(robustness={"likely_artifact": True})])
    assert gated["visible"] == []
    assert gated["technical_excluded"][0]["display_gate_reason"] == "likely_artifact_flag"


def test_clinical_candidate_is_exploratory(monkeypatch):
    monkeypatch.setattr(
        "pipeline_core.display_gating.lookup_compound",
        lambda **kwargs: {
            "human_development_status": "investigational",
            "entity_type": "clinical_candidate",
            "display_action": "exploratory_only",
            "display_gate_reason": "clinical_candidate_not_approved",
            "match_key": "canonical",
            "breast_oncology_relevance": "investigational_breast",
            "withdrawn_or_discontinued": False,
            "sources": [],
        },
    )
    annotated = annotate_human_development(_row(drug="veliparib", canonical="veliparib"))
    assert annotated["display_action"] == "exploratory_only"
    assert annotated["list1_percentile"] == 0.91
