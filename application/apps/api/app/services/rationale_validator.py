"""Ground LLM rationale claims against an immutable analysis payload."""

from __future__ import annotations

import re
from typing import Any

from pipeline_core.safety import check_safety

from app.schemas.rationale import GroundedRationaleResponse, RationaleClaim

_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?")


def flatten_payload(payload: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat[path] = value
            flat.update(flatten_payload(value, path))
    elif isinstance(payload, list):
        for index, value in enumerate(payload[:25]):
            path = f"{prefix}[{index}]"
            flat[path] = value
            if isinstance(value, (dict, list)):
                flat.update(flatten_payload(value, path))
    return flat


def allowed_values(payload: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for value in flatten_payload(payload).values():
        if value is None or isinstance(value, (dict, list)):
            continue
        text = str(value)
        values.add(text.lower())
        if isinstance(value, float):
            values.add(f"{value:.2f}")
            values.add(f"{value:.0%}")
            values.add(f"{value:.1%}")
        if isinstance(value, (int, float)):
            values.add(str(value))
    return values


def _allowed_citation_ids(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for row in payload.get("overlap_nominations") or []:
        lit = (row or {}).get("literature_summary") or {}
        for citation in lit.get("top_citations") or []:
            for key in ("doi", "pmid", "pmcid"):
                if citation.get(key):
                    ids.add(str(citation[key]))
    return ids


def _claim_numbers_ok(text: str, values: set[str]) -> bool:
    for match in _NUMBER_RE.findall(text):
        token = match.lower().rstrip("%")
        if token in values or match.lower() in values:
            continue
        # Cluster ids and ranks like 0/1/2/3/4 and small integers appear often.
        try:
            as_int = int(token)
        except ValueError:
            return False
        if as_int <= 500 and (str(as_int) in values or token in values):
            continue
        return False
    return True


def validate_rationale(raw: dict, payload: dict[str, Any]) -> GroundedRationaleResponse:
    parsed = GroundedRationaleResponse.model_validate(raw)
    flat = flatten_payload(payload)
    values = allowed_values(payload)
    citation_ids = _allowed_citation_ids(payload)
    claims = [*parsed.supporting_claims, *parsed.counter_claims, *parsed.uncertainty]
    if check_safety(parsed.summary):
        raise ValueError("unsafe summary language")
    for claim in claims:
        if check_safety(claim.text):
            raise ValueError("unsafe claim language")
        if not claim.evidence_keys:
            raise ValueError("claim missing evidence_keys")
        for key in claim.evidence_keys:
            if key not in flat:
                raise ValueError(f"unknown evidence key {key}")
        for citation_id in claim.citation_ids:
            if citation_ids and citation_id not in citation_ids:
                raise ValueError(f"unknown citation id {citation_id}")
        if not _claim_numbers_ok(claim.text, values):
            raise ValueError("ungrounded numeric claim")
    return parsed


def claims_to_prose(rationale: GroundedRationaleResponse) -> str:
    parts = [rationale.summary]
    for claim in rationale.supporting_claims[:4]:
        parts.append(claim.text)
    if rationale.counter_claims:
        parts.append(rationale.counter_claims[0].text)
    if rationale.uncertainty:
        parts.append(rationale.uncertainty[0].text)
    return " ".join(parts)
