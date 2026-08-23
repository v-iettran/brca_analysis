"""ClinicalTrials.gov search with SQLite caching and run-level aggregation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import httpx
from sqlalchemy.orm import Session

from app.adapters.clinicaltrials_client import find_trials_for_drug, trial_match_to_dict
from app.config import get_settings
from app.models_orm import AnalysisRun, ExternalQueryCache
from app.services.literature_service import _is_fresh

settings = get_settings()


def _cache_key(drug: str, metadata: dict) -> str:
    payload = json.dumps({"drug": drug, "metadata": metadata, "v": 2}, sort_keys=True, default=str)
    return "clinicaltrials:" + hashlib.sha256(payload.encode()).hexdigest()


def search_trials_for_drug(db: Session, drug: str, patient_metadata: dict) -> dict:
    cache_key = _cache_key(drug, patient_metadata)
    cached = db.get(ExternalQueryCache, cache_key)
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    if cached and _is_fresh(cached.fetched_at):
        result = dict(cached.response_json)
        result["cache_hit"] = True
        return result

    if not settings.allow_external_queries:
        return {
            "drug": drug,
            "trials": [],
            "cache_hit": False,
            "searched_at": now,
            "unavailable_reason": "External queries are disabled (ALLOW_EXTERNAL_QUERIES=false).",
        }

    try:
        with httpx.Client() as client:
            matches = find_trials_for_drug(client, drug, patient_metadata)
    except httpx.HTTPError as exc:
        return {
            "drug": drug,
            "trials": [],
            "cache_hit": False,
            "searched_at": now,
            "unavailable_reason": f"ClinicalTrials.gov request failed: {exc}",
        }

    result = {
        "drug": drug,
        "trials": [trial_match_to_dict(m) for m in matches],
        "cache_hit": False,
        "searched_at": now,
    }

    db.merge(
        ExternalQueryCache(
            cache_key=cache_key,
            service="clinicaltrials",
            query_text=f"drug={drug}",
            response_json=result,
        )
    )
    db.commit()
    return result


def search_trials_for_run(db: Session, run: AnalysisRun, max_drugs: int = 8) -> dict:
    """Aggregate and deduplicate trials across overlap nominations."""
    payload = run.result_payload or {}
    nominations = payload.get("overlap_nominations") or payload.get("top_candidate_drugs") or []
    metadata = run.patient_metadata or {}
    drugs = []
    for row in nominations:
        drug = row.get("drug")
        if drug and drug not in drugs:
            drugs.append(drug)
        if len(drugs) >= max_drugs:
            break

    by_nct: dict[str, dict] = {}
    unavailable = []
    for drug in drugs:
        result = search_trials_for_drug(db, drug, metadata)
        if result.get("unavailable_reason"):
            unavailable.append({"drug": drug, "reason": result["unavailable_reason"]})
            continue
        for trial in result.get("trials", []):
            nct = trial["nct_id"]
            if nct not in by_nct:
                entry = dict(trial)
                entry["matched_drugs"] = [drug]
                by_nct[nct] = entry
            else:
                if drug not in by_nct[nct]["matched_drugs"]:
                    by_nct[nct]["matched_drugs"].append(drug)

    trials = list(by_nct.values())

    def sort_key(t: dict):
        assessment = t.get("eligibility_assessment")
        eligibility_rank = {
            "potentially_eligible": 0,
            "insufficient_information": 1,
            "potentially_ineligible": 2,
        }.get(assessment, 3)
        criteria = t.get("eligibility_criteria") or []
        known = sum(1 for c in criteria if c.get("status") in {"met", "not_met"})
        completeness = -known
        status = str(t.get("status") or "").lower()
        status_rank = 0 if "recruit" in status else (1 if "not yet" in status else 2)
        # Prefer nominations that also have stronger evidence tiers when available.
        tier_bonus = 0
        for drug in t.get("matched_drugs") or []:
            for row in nominations:
                if row.get("drug") == drug:
                    tier = str(row.get("evidence_tier") or "")
                    if tier.startswith("tier_a"):
                        tier_bonus = min(tier_bonus, -2)
                    elif tier.startswith("tier_b"):
                        tier_bonus = min(tier_bonus, -1)
        tier = t["sites"][0]["tier"] if t.get("sites") else 99
        dist = t["sites"][0].get("distance_from_ireland_km") if t.get("sites") else 1e9
        return (eligibility_rank, completeness, status_rank, tier_bonus, tier, dist or 1e9)

    trials.sort(key=sort_key)
    return {
        "run_id": run.run_id,
        "patient_label": run.patient_label,
        "n_drugs_queried": len(drugs),
        "drugs_queried": drugs,
        "trials": trials,
        "n_trials": len(trials),
        "unavailable": unavailable,
        "interpretation": (
            "Potential match means no known exclusion was found in parsed criteria. "
            "Unknown criteria remain visible and require investigator confirmation. "
            "This is not an eligibility determination."
        ),
    }
