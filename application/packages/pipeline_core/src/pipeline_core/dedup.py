"""Citation deduplication and rule-based support/conflict pre-labeling.

Dedup priority: DOI, then PMID/PMC ID, then normalized title+year. The local
LLM (see ``apps/api/app/adapters/ollama_client.py``) may reclassify
``unclear`` items into supporting/conflicting/neutral using the retained
excerpt, but it never invents citations or metadata this module did not
already extract from Paperclip/ClinicalTrials.gov responses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

StanceLabel = Literal["supporting", "conflicting", "neutral", "unclear"]

_SUPPORTING_PATTERNS = [
    r"\beffective\b",
    r"\bimproved (survival|response|outcome)\b",
    r"\bsignificant(ly)? (benefit|improvement|response)\b",
    r"\bwell[- ]tolerated\b",
    r"\bsuperior to\b",
]
_CONFLICTING_PATTERNS = [
    r"\bno (significant )?(benefit|difference|improvement)\b",
    r"\bfailed to (show|demonstrate)\b",
    r"\bresistan(t|ce)\b",
    r"\badverse event[s]?\b",
    r"\bdid not (meet|improve)\b",
    r"\binferior to\b",
]


@dataclass
class Citation:
    title: str
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    journal: str | None = None
    publisher: str | None = None
    # The repository a record came from (PMC, bioRxiv, arXiv...). Distinct from
    # `journal`: it separates a peer-reviewed article from a preprint, which the
    # panel shows because it changes how much weight a reader should give it.
    source: str | None = None
    article_type: str | None = None
    peer_reviewed: bool | None = None
    full_text_available: bool | None = None
    excerpt: str | None = None
    source_query: str | None = None
    raw: dict = field(default_factory=dict)

    def dedup_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.strip().lower()}"
        if self.pmid:
            return f"pmid:{self.pmid.strip()}"
        if self.pmcid:
            return f"pmcid:{self.pmcid.strip()}"
        normalized_title = re.sub(r"[^a-z0-9]+", " ", (self.title or "").lower()).strip()
        return f"title:{normalized_title}:{self.year or ''}"


def deduplicate_citations(citations: list[Citation]) -> list[Citation]:
    """Keep the first-seen citation per dedup key, merging the query
    provenance of later duplicates so the citation popup can show every
    query family that surfaced the same paper."""
    seen: dict[str, Citation] = {}
    query_history: dict[str, list[str]] = {}
    for citation in citations:
        key = citation.dedup_key()
        query_history.setdefault(key, [])
        if citation.source_query:
            query_history[key].append(citation.source_query)
        if key not in seen:
            seen[key] = citation

    for key, citation in seen.items():
        citation.raw["matched_queries"] = sorted(set(query_history[key]))
    return list(seen.values())


def rule_based_stance(excerpt: str | None) -> StanceLabel:
    """A conservative, explainable first pass before the local LLM is asked
    to classify ambiguous excerpts. Both supporting and conflicting language
    present -> unclear rather than guessing."""
    if not excerpt:
        return "unclear"
    text = excerpt.lower()
    supports = any(re.search(p, text) for p in _SUPPORTING_PATTERNS)
    conflicts = any(re.search(p, text) for p in _CONFLICTING_PATTERNS)
    if supports and conflicts:
        return "unclear"
    if supports:
        return "supporting"
    if conflicts:
        return "conflicting"
    return "neutral"
