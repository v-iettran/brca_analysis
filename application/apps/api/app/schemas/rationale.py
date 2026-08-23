from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RationaleClaim(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    kind: Literal["support", "counter", "uncertainty"] = "support"
    evidence_keys: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    section: Literal["patient", "mofa", "q5", "drug", "trial", "literature"] = "drug"


class GroundedRationaleResponse(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    supporting_claims: list[RationaleClaim] = Field(default_factory=list)
    counter_claims: list[RationaleClaim] = Field(default_factory=list)
    uncertainty: list[RationaleClaim] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    used_llm: bool = False
    fallback_used: bool = True
    provider: str | None = None
    model: str | None = None
