"""ClinicalTrials.gov API v2 adapter (https://clinicaltrials.gov/api/v2/studies).

Restricted to Europe + US per the plan; site ordering delegates to
``pipeline_core.geography`` (Ireland first, then rest of Europe, then US).
Eligibility is matched conservatively with per-criterion
``met`` / ``not_met`` / ``unknown`` statuses. A trial is only a potential
match when no known exclusion is found; unknowns remain visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx

from pipeline_core.geography import rank_sites

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
ALLOWED_COUNTRIES = {
    "ireland",
    "united kingdom",
    "france",
    "germany",
    "spain",
    "italy",
    "netherlands",
    "belgium",
    "switzerland",
    "austria",
    "portugal",
    "sweden",
    "denmark",
    "norway",
    "finland",
    "poland",
    "united states",
}

_HER2_NEGATIVE_REQUIRED = re.compile(r"her2[\s-]*(negative|non-amplified|ihc\s*0|ihc\s*1\+?)", re.IGNORECASE)
_HER2_POSITIVE_REQUIRED = re.compile(r"her2[\s-]*(positive|amplified|ihc\s*3\+)", re.IGNORECASE)
_ER_POSITIVE_REQUIRED = re.compile(r"(er|estrogen receptor)[\s-]*positive", re.IGNORECASE)
_ER_NEGATIVE_REQUIRED = re.compile(r"(er|estrogen receptor)[\s-]*negative", re.IGNORECASE)
_MIN_AGE_PATTERN = re.compile(r"(\d{1,3})\s*years", re.IGNORECASE)


@dataclass
class TrialQuery:
    condition: str = "breast cancer"
    intervention: str | None = None
    status: str = "RECRUITING"
    page_size: int = 20


@dataclass
class TrialSiteInfo:
    facility: str | None
    city: str | None
    country: str | None
    tier: int
    distance_from_ireland_km: float | None


@dataclass
class EligibilityCriterion:
    criterion: str
    status: str  # met | not_met | unknown
    evidence: str
    source_excerpt: str | None = None


@dataclass
class TrialMatch:
    nct_id: str
    title: str
    status: str
    phase: str | None
    conditions: list[str]
    interventions: list[str]
    sites: list[TrialSiteInfo]
    eligibility_criteria_text: str
    eligibility_assessment: str
    eligibility_notes: list[str] = field(default_factory=list)
    eligibility_criteria: list[EligibilityCriterion] = field(default_factory=list)
    url: str = ""


def search_trials(client: httpx.Client, query: TrialQuery) -> list[dict]:
    params = {
        "query.cond": query.condition,
        "filter.overallStatus": query.status,
        "pageSize": query.page_size,
        "format": "json",
    }
    if query.intervention:
        params["query.intr"] = query.intervention

    response = client.get(BASE_URL, params=params, timeout=20.0)
    response.raise_for_status()
    return response.json().get("studies", [])


def _extract_sites(study: dict) -> list[TrialSiteInfo]:
    locations = (
        study.get("protocolSection", {}).get("contactsLocationsModule", {}).get("locations", [])
    )
    filtered_locations = [
        loc for loc in locations if (loc.get("country") or "").strip().lower() in ALLOWED_COUNTRIES
    ]
    if not filtered_locations:
        return []

    ranked = rank_sites([loc.get("country") for loc in filtered_locations])
    site_infos = []
    for loc, rank in zip(filtered_locations, ranked):
        site_infos.append(
            TrialSiteInfo(
                facility=loc.get("facility"),
                city=loc.get("city"),
                country=loc.get("country"),
                tier=rank.tier,
                distance_from_ireland_km=rank.distance_from_ireland_km,
            )
        )
    site_infos.sort(key=lambda s: (s.tier, s.distance_from_ireland_km or 1e9))
    return site_infos


def _her2_label(raw: str) -> str:
    value = (raw or "").strip().lower()
    if "posit" in value or "gain" in value:
        return "positive"
    if "negat" in value or "neutral" in value or "loss" in value:
        return "negative"
    return "unknown"


def _er_label(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value.startswith("posit"):
        return "positive"
    if value.startswith("neg"):
        return "negative"
    return "unknown"


def assess_eligibility_criteria(eligibility_text: str, patient_metadata: dict) -> list[EligibilityCriterion]:
    criteria: list[EligibilityCriterion] = []
    her2 = _her2_label(str(patient_metadata.get("her2_status") or ""))
    er = _er_label(str(patient_metadata.get("er_status") or ""))
    pr = _er_label(str(patient_metadata.get("pr_status") or ""))
    age = patient_metadata.get("age_at_diagnosis")
    ecog = patient_metadata.get("ecog_status")
    stage = str(patient_metadata.get("tumor_stage") or "")

    her2_neg = _HER2_NEGATIVE_REQUIRED.search(eligibility_text)
    her2_pos = _HER2_POSITIVE_REQUIRED.search(eligibility_text)
    if her2_neg:
        excerpt = her2_neg.group(0)
        if her2 == "negative":
            criteria.append(EligibilityCriterion("HER2-negative requirement", "met", "Patient HER2 appears negative.", excerpt))
        elif her2 == "positive":
            criteria.append(EligibilityCriterion("HER2-negative requirement", "not_met", "Patient HER2 appears positive.", excerpt))
        else:
            criteria.append(EligibilityCriterion("HER2-negative requirement", "unknown", "Patient HER2 status unavailable.", excerpt))
    if her2_pos:
        excerpt = her2_pos.group(0)
        if her2 == "positive":
            criteria.append(EligibilityCriterion("HER2-positive requirement", "met", "Patient HER2 appears positive.", excerpt))
        elif her2 == "negative":
            criteria.append(EligibilityCriterion("HER2-positive requirement", "not_met", "Patient HER2 appears negative.", excerpt))
        else:
            criteria.append(EligibilityCriterion("HER2-positive requirement", "unknown", "Patient HER2 status unavailable.", excerpt))

    er_pos = _ER_POSITIVE_REQUIRED.search(eligibility_text)
    er_neg = _ER_NEGATIVE_REQUIRED.search(eligibility_text)
    if er_pos:
        excerpt = er_pos.group(0)
        if er == "positive":
            criteria.append(EligibilityCriterion("ER-positive requirement", "met", "Patient ER appears positive.", excerpt))
        elif er == "negative":
            criteria.append(EligibilityCriterion("ER-positive requirement", "not_met", "Patient ER appears negative.", excerpt))
        else:
            criteria.append(EligibilityCriterion("ER-positive requirement", "unknown", "Patient ER status unavailable.", excerpt))
    if er_neg:
        excerpt = er_neg.group(0)
        if er == "negative":
            criteria.append(EligibilityCriterion("ER-negative requirement", "met", "Patient ER appears negative.", excerpt))
        elif er == "positive":
            criteria.append(EligibilityCriterion("ER-negative requirement", "not_met", "Patient ER appears positive.", excerpt))
        else:
            criteria.append(EligibilityCriterion("ER-negative requirement", "unknown", "Patient ER status unavailable.", excerpt))

    if re.search(r"\bPR[\s-]*positive|progesterone receptor[\s-]*positive", eligibility_text, re.I):
        excerpt = "PR-positive"
        if pr == "positive":
            criteria.append(EligibilityCriterion("PR-positive requirement", "met", "Patient PR appears positive.", excerpt))
        elif pr == "negative":
            criteria.append(EligibilityCriterion("PR-positive requirement", "not_met", "Patient PR appears negative.", excerpt))
        else:
            criteria.append(EligibilityCriterion("PR-positive requirement", "unknown", "Patient PR status unavailable or demo-generated.", excerpt))

    min_age_match = _MIN_AGE_PATTERN.search(eligibility_text)
    if min_age_match:
        min_age = float(min_age_match.group(1))
        excerpt = min_age_match.group(0)
        if age is None:
            criteria.append(EligibilityCriterion("Minimum age", "unknown", "Patient age unavailable.", excerpt))
        elif age < min_age:
            criteria.append(EligibilityCriterion("Minimum age", "not_met", f"Patient age {age:.0f} < {min_age:.0f}.", excerpt))
        else:
            criteria.append(EligibilityCriterion("Minimum age", "met", f"Patient age {age:.0f} meets minimum {min_age:.0f}.", excerpt))

    ecog_match = re.search(r"ECOG.*?([0-2])", eligibility_text, re.I)
    if ecog_match:
        max_ecog = int(ecog_match.group(1))
        excerpt = ecog_match.group(0)
        if ecog is None:
            criteria.append(EligibilityCriterion("ECOG performance status", "unknown", "ECOG not available (demo field if present).", excerpt))
        elif int(ecog) <= max_ecog:
            criteria.append(EligibilityCriterion("ECOG performance status", "met", f"Patient ECOG {ecog} <= {max_ecog}.", excerpt))
        else:
            criteria.append(EligibilityCriterion("ECOG performance status", "not_met", f"Patient ECOG {ecog} > {max_ecog}.", excerpt))

    if re.search(r"stage\s+(IV|4|III|3|II|2)", eligibility_text, re.I):
        excerpt = "stage requirement mentioned"
        if not stage:
            criteria.append(EligibilityCriterion("Stage requirement", "unknown", "Tumor stage unavailable or demo-generated.", excerpt))
        else:
            criteria.append(
                EligibilityCriterion(
                    "Stage requirement",
                    "unknown",
                    f"Patient stage labeled {stage}; clinician must confirm against full protocol text.",
                    excerpt,
                )
            )

    if not criteria:
        criteria.append(
            EligibilityCriterion(
                "General eligibility",
                "unknown",
                "No explicit biomarker/age/ECOG criteria could be parsed confidently from the public eligibility text.",
                None,
            )
        )
    return criteria


def assess_eligibility(eligibility_text: str, patient_metadata: dict) -> tuple[str, list[str]]:
    criteria = assess_eligibility_criteria(eligibility_text, patient_metadata)
    notes = [f"{c.criterion}: {c.status} — {c.evidence}" for c in criteria]
    if any(c.status == "not_met" for c in criteria):
        return "potentially_ineligible", notes
    # Require at least one disease/biomarker criterion to be met, not only age.
    disease_like = {
        "HER2-negative requirement",
        "HER2-positive requirement",
        "ER-positive requirement",
        "ER-negative requirement",
        "PR-positive requirement",
        "Stage requirement",
        "ECOG performance status",
    }
    if any(c.status == "met" and c.criterion in disease_like for c in criteria):
        return "potentially_eligible", notes
    if any(c.status == "met" for c in criteria):
        # Age-only / weak matches stay insufficient for clinician "potential match".
        return "insufficient_information", notes
    return "insufficient_information", notes


def _breast_cancer_relevant(study: dict, title: str, conditions: list[str]) -> bool:
    blob = " ".join([title, *conditions]).lower()
    return any(
        term in blob
        for term in (
            "breast",
            "mammary",
            "triple-negative",
            "tnbc",
            "her2",
            "metastatic breast",
            "ductal carcinoma",
        )
    )


def parse_study(study: dict, patient_metadata: dict) -> TrialMatch | None:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    interventions_module = protocol.get("armsInterventionsModule", {})
    eligibility_module = protocol.get("eligibilityModule", {})

    sites = _extract_sites(study)
    if not sites:
        return None

    title = identification.get("briefTitle", "") or ""
    conditions = conditions_module.get("conditions", []) or []
    if not _breast_cancer_relevant(study, title, conditions):
        return None

    eligibility_text = eligibility_module.get("eligibilityCriteria", "")
    criteria = assess_eligibility_criteria(eligibility_text, patient_metadata)
    assessment, notes = assess_eligibility(eligibility_text, patient_metadata)

    nct_id = identification.get("nctId", "")
    return TrialMatch(
        nct_id=nct_id,
        title=title,
        status=status_module.get("overallStatus", ""),
        phase=(design_module.get("phases") or [None])[0],
        conditions=conditions,
        interventions=[i.get("name", "") for i in interventions_module.get("interventions", [])],
        sites=sites,
        eligibility_criteria_text=eligibility_text,
        eligibility_assessment=assessment,
        eligibility_notes=notes,
        eligibility_criteria=criteria,
        url=f"https://clinicaltrials.gov/study/{nct_id}",
    )


def find_trials_for_drug(
    client: httpx.Client, drug: str, patient_metadata: dict, condition: str = "breast cancer"
) -> list[TrialMatch]:
    studies = search_trials(client, TrialQuery(condition=condition, intervention=drug))
    matches = [parse_study(s, patient_metadata) for s in studies]
    valid = [m for m in matches if m is not None]
    valid.sort(key=lambda m: (m.sites[0].tier, m.sites[0].distance_from_ireland_km or 1e9))
    return valid


def trial_match_to_dict(m: TrialMatch) -> dict:
    return {
        "nct_id": m.nct_id,
        "title": m.title,
        "status": m.status,
        "phase": m.phase,
        "conditions": m.conditions,
        "interventions": m.interventions,
        "sites": [
            {
                "facility": s.facility,
                "city": s.city,
                "country": s.country,
                "tier": s.tier,
                "distance_from_ireland_km": s.distance_from_ireland_km,
            }
            for s in m.sites
        ],
        "eligibility_assessment": m.eligibility_assessment,
        "eligibility_notes": m.eligibility_notes,
        "eligibility_criteria": [
            {
                "criterion": c.criterion,
                "text": c.criterion,
                "status": c.status,
                "evidence": c.evidence,
                "rationale": c.evidence,
                "source_excerpt": c.source_excerpt,
                "category": None,
            }
            for c in m.eligibility_criteria
        ],
        "eligibility_criteria_text": m.eligibility_criteria_text,
        "url": m.url,
    }
