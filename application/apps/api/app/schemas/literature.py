from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CitationOut(BaseModel):
    title: str
    year: int | None
    doi: str | None
    pmid: str | None
    pmcid: str | None
    journal: str | None
    publisher: str | None
    source: str | None = None
    article_type: str | None
    peer_reviewed: bool | None
    full_text_available: bool | None
    excerpt: str | None
    stance: Literal["supporting", "conflicting", "neutral", "unclear"]
    matched_queries: list[str]
    credibility_score: float | None = None
    relevance_score: float | None = None
    combined_score: float | None = None
    evidence_rank: int | None = None
    ranking_explanation: str | None = None


class LiteratureQueryFamily(BaseModel):
    label: str
    query_text: str
    result_count: int
    executed_at: str


class LiteratureResult(BaseModel):
    drug: str
    query_families: list[LiteratureQueryFamily]
    citations: list[CitationOut]
    deduplicated_count: int
    raw_result_count: int
    cache_hit: bool
    searched_at: str
