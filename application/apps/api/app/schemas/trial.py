from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TrialSite(BaseModel):
    facility: str | None
    city: str | None
    country: str | None
    tier: int
    distance_from_ireland_km: float | None


class EligibilityCriterionOut(BaseModel):
    criterion: str
    status: Literal["met", "not_met", "unknown"]
    evidence: str
    source_excerpt: str | None = None


class TrialMatchOut(BaseModel):
    nct_id: str
    title: str
    status: str
    phase: str | None
    conditions: list[str]
    interventions: list[str]
    sites: list[TrialSite]
    eligibility_assessment: Literal[
        "potentially_eligible", "potentially_ineligible", "insufficient_information"
    ]
    eligibility_notes: list[str]
    eligibility_criteria: list[EligibilityCriterionOut] = []
    eligibility_criteria_text: str | None = None
    matched_drugs: list[str] = []
    url: str
