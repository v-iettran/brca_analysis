"""Post-ranking display gating for human-development status.

Scoring, ranks, and percentiles are never recomputed here. This module only
annotates overlap rows and partitions them into default-visible, exploratory,
and technical-excluded presentation lanes.
"""

from __future__ import annotations

from pipeline_core.compound_registry import (
    human_development_label,
    is_anonymous_perturbagen,
    lookup_compound,
    registry_version,
)

UNRESOLVED_RECORD = {
    "entity_type": "unresolved",
    "human_development_status": "unresolved",
    "breast_oncology_relevance": "unknown",
    "withdrawn_or_discontinued": False,
    "display_action": "technical_excluded",
    "display_gate_reason": "unresolved_not_in_registry",
    "match_key": "none",
    "sources": [],
}


def annotate_human_development(row: dict) -> dict:
    """Return a copy of ``row`` with registry fields; ranks are untouched."""
    out = dict(row)
    canonical = str(out.get("canonical") or out.get("drug") or "")
    pert_id = out.get("pert_id") or out.get("lincs_pert_id")
    inchi_key = out.get("inchi_key")
    robustness = out.get("robustness") or {}

    if is_anonymous_perturbagen(canonical, pert_id):
        record = {
            **UNRESOLVED_RECORD,
            "entity_type": "non_therapeutic_perturbagen",
            "human_development_status": "non_drug_perturbagen",
            "display_gate_reason": "anonymous_lincs_identifier",
            "match_key": "anonymous_id",
        }
    else:
        record = lookup_compound(name=canonical, pert_id=pert_id, inchi_key=inchi_key)
        if record is None:
            record = dict(UNRESOLVED_RECORD)

    display_action = record.get("display_action") or "technical_excluded"
    reason = record.get("display_gate_reason") or "unresolved_not_in_registry"
    if robustness.get("likely_artifact"):
        display_action = "technical_excluded"
        reason = "likely_artifact_flag"

    out["human_development_status"] = record.get("human_development_status") or "unresolved"
    out["human_development_label"] = human_development_label(out["human_development_status"])
    out["entity_type"] = record.get("entity_type") or "unresolved"
    out["breast_oncology_relevance"] = record.get("breast_oncology_relevance") or "unknown"
    out["withdrawn_or_discontinued"] = bool(record.get("withdrawn_or_discontinued"))
    out["display_action"] = display_action
    out["display_gate_reason"] = reason
    out["registry_match_key"] = record.get("match_key") or "none"
    out["registry_sources"] = list(record.get("sources") or [])
    return out


def apply_display_gating(overlap_rows: list[dict]) -> dict:
    """Partition annotated overlap rows without changing rank fields."""
    visible: list[dict] = []
    exploratory: list[dict] = []
    excluded: list[dict] = []
    for row in overlap_rows:
        annotated = annotate_human_development(row)
        action = annotated.get("display_action")
        if action == "default_visible":
            visible.append(annotated)
        elif action == "exploratory_only":
            exploratory.append(annotated)
        else:
            excluded.append(annotated)

    return {
        "visible": visible,
        "exploratory": exploratory,
        "technical_excluded": excluded,
        "registry_version": registry_version(),
        "gate_summary": {
            "n_input": len(overlap_rows),
            "n_default_visible": len(visible),
            "n_exploratory_only": len(exploratory),
            "n_technical_excluded": len(excluded),
            "ranking_preserved": True,
        },
    }
