"""Paperclip literature adapter (https://paperclip.gxl.ai/).

Uses the official ``gxl_paperclip`` Python SDK
(``PaperclipClient.from_env()``, reading ``PAPERCLIP_API_KEY``). The key is
never logged, returned in an API response, or written to the SQLite cache --
only the resulting citation metadata is persisted.

For each nominated drug we run four explicit, separately-recorded query
families (see plan): exact drug/synonyms + breast cancer; drug + targets +
breast cancer; drug + systematic review/meta-analysis; drug +
resistance/adverse/conflicting evidence. Every family's raw query text and
result count is retained so the citation popup can show exactly what was
searched.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Protocol

from pipeline_core.dedup import Citation, deduplicate_citations, rule_based_stance


class PaperclipClientProtocol(Protocol):
    def search(self, query: str, *, limit: int | None = None, source: str | None = None, type: str | None = None): ...


class PaperclipUnavailableError(RuntimeError):
    """Raised when the SDK is not installed or no API key is configured."""


SEARCH_TIMEOUT_SECONDS = 8.0


def _search_with_timeout(client: PaperclipClientProtocol, query_text: str, kwargs: dict):
    """Bound a Paperclip search so a hung vendor call cannot stall analysis."""
    box: dict = {}

    def _call(q=query_text, k=dict(kwargs)):
        try:
            box["result"] = client.search(q, **k)
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    worker = threading.Thread(target=_call, daemon=True, name="paperclip-search")
    worker.start()
    worker.join(timeout=SEARCH_TIMEOUT_SECONDS)
    if worker.is_alive() or "error" in box:
        return None
    return box.get("result")


def get_paperclip_client() -> PaperclipClientProtocol | None:
    try:
        from gxl_paperclip import PaperclipClient
    except ImportError:
        return None
    try:
        import os

        from app.config import get_settings

        # Settings loads apps/api/.env; PaperclipClient.from_env reads os.environ.
        # Accept the short name too: the key is commonly exported as PAPERCLIP.
        key = (
            get_settings().paperclip_api_key
            or os.environ.get("PAPERCLIP_API_KEY")
            or os.environ.get("PAPERCLIP")
        )
        if not key:
            return None
        os.environ["PAPERCLIP_API_KEY"] = key
        return PaperclipClient.from_env()
    except Exception:
        return None


@dataclass
class QueryFamilyResult:
    label: str
    query_text: str
    result_count: int
    citations: list[Citation]


DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>]+\b")
PMID_PATTERN = re.compile(r"\bPMID:?\s*(\d{5,9})\b", re.IGNORECASE)
PMCID_PATTERN = re.compile(r"\b(PMC\d{5,10})\b", re.IGNORECASE)


def _structured_records(result) -> list | None:
    """The structured paper list, wherever this SDK version keeps it.

    ``ExecuteResult.papers`` is the documented accessor and reads
    ``result_data["papers"|"results"]``. Older adapters looked only at ``raw``,
    which is the HTTP envelope and does not hold the hit list -- so the
    structured branch never ran and everything fell through to text parsing.
    Both are tried, newest first, and a list-shaped ``raw`` is still honoured.
    """
    papers = getattr(result, "papers", None)
    if isinstance(papers, list) and papers:
        return papers

    data = getattr(result, "result_data", None)
    if isinstance(data, dict):
        records = data.get("papers") or data.get("results") or data.get("documents")
        if records:
            return records

    raw = getattr(result, "raw", None)
    if isinstance(raw, dict):
        return raw.get("results") or raw.get("papers") or raw.get("documents")
    if isinstance(raw, list):
        return raw
    return None


def _parse_result_to_citations(result, query_text: str) -> list[Citation]:
    """Best-effort structured parse of an ``ExecuteResult``.

    Prefers the SDK's own structured hit list; falls back to light regex
    extraction over ``result.output`` so the adapter degrades gracefully rather
    than raising if the shape changes.

    The fallback loses almost everything. ``output`` is the formatted text the
    CLI prints, and carries no year, journal or source, so a run that lands here
    yields citations that can only be shown as a title and a link. That is what
    every record looked like until this function learned to read
    ``result.papers``.
    """
    citations: list[Citation] = []
    records = _structured_records(result)

    if records:
        for record in records:
            if not isinstance(record, dict):
                continue
            citations.append(
                Citation(
                    title=record.get("title") or "(untitled)",
                    year=_safe_int(record.get("year") or record.get("date")),
                    doi=record.get("doi"),
                    pmid=str(record.get("pmid")) if record.get("pmid") else None,
                    pmcid=record.get("pmcid") or record.get("pmc_id") or record.get("pmc"),
                    journal=record.get("journal"),
                    publisher=record.get("publisher"),
                    source=record.get("source"),
                    article_type=record.get("type") or record.get("article_type"),
                    peer_reviewed=record.get("peer_reviewed"),
                    full_text_available=record.get("full_text_available"),
                    excerpt=(
                        record.get("abstract")
                        or record.get("excerpt")
                        or record.get("snippet")
                        or ""
                    )[:600]
                    or None,
                    source_query=query_text,
                    raw=record,
                )
            )
        return citations

    output_text = getattr(result, "output", "") or ""
    for block in output_text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        # SDK output has a header/footer plus one numbered block per paper.
        # Keep only actual paper blocks to avoid counting "Found N papers" and
        # timing/help text as citations.
        title_match = re.match(r"^\s*\d+\.\s+(.+)$", lines[0])
        if not title_match:
            continue
        title_line = title_match.group(1).strip()[:300]
        doi_match = DOI_PATTERN.search(block)
        pmid_match = PMID_PATTERN.search(block)
        pmcid_match = PMCID_PATTERN.search(block)
        excerpt = None
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith('"') and len(stripped) > 2:
                excerpt = stripped.strip('"')[:600]
                break
        citations.append(
            Citation(
                title=title_line,
                doi=doi_match.group(0).rstrip(".,);]") if doi_match else None,
                pmid=pmid_match.group(1) if pmid_match else None,
                pmcid=pmcid_match.group(1).upper() if pmcid_match else None,
                excerpt=excerpt or block.strip()[:600],
                source_query=query_text,
                raw={"unparsed_block": block},
            )
        )
    return citations


def _safe_int(value) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def build_query_families(drug: str, targets: list[str], synonyms: list[str] | None = None) -> list[tuple[str, str]]:
    synonyms = synonyms or []
    drug_terms = " OR ".join([drug, *synonyms]) if synonyms else drug
    target_terms = " ".join(targets[:5])
    return [
        ("exact_drug_breast_cancer", f'"{drug_terms}" breast cancer'),
        (
            "drug_targets_breast_cancer",
            f"{drug} {target_terms} breast cancer".strip(),
        ),
        ("systematic_review_meta_analysis", f"{drug} breast cancer systematic review meta-analysis"),
        ("resistance_adverse_conflicting", f"{drug} breast cancer resistance adverse conflicting evidence"),
    ]


def build_gene_query_families(gene: str) -> list[tuple[str, str]]:
    """Transparent query families for literature context around one gene.

    Literature volume is context only and must not be interpreted as
    validation of the cluster coefficient or as a measure of gene importance.
    """
    symbol = gene.strip().upper()
    return [
        ("gene_breast_cancer", f'"{symbol}" breast cancer'),
        (
            "systematic_review_meta_analysis",
            f'"{symbol}" breast cancer systematic review meta-analysis',
        ),
        (
            "expression_prognosis_therapy",
            f'"{symbol}" breast cancer expression prognosis therapy',
        ),
        (
            "resistance_conflicting_evidence",
            f'"{symbol}" breast cancer resistance conflicting evidence',
        ),
    ]


def search_drug_literature(
    client: PaperclipClientProtocol, drug: str, targets: list[str], synonyms: list[str] | None = None
) -> list[QueryFamilyResult]:
    families = build_query_families(drug, targets, synonyms)
    results = []
    for label, query_text in families:
        kwargs = {"limit": 15, "source": "pmc"}
        if label == "systematic_review_meta_analysis":
            kwargs["type"] = "review-article"
        result = _search_with_timeout(client, query_text, kwargs)
        citations = _parse_result_to_citations(result, query_text) if result is not None else []
        results.append(
            QueryFamilyResult(label=label, query_text=query_text, result_count=len(citations), citations=citations)
        )
    return results


def search_gene_literature(
    client: PaperclipClientProtocol, gene: str
) -> list[QueryFamilyResult]:
    results = []
    for label, query_text in build_gene_query_families(gene):
        kwargs = {"limit": 12, "source": "pmc"}
        if label == "systematic_review_meta_analysis":
            kwargs["type"] = "review-article"
        result = _search_with_timeout(client, query_text, kwargs)
        citations = _parse_result_to_citations(result, query_text) if result is not None else []
        results.append(
            QueryFamilyResult(
                label=label,
                query_text=query_text,
                result_count=len(citations),
                citations=citations,
            )
        )
    return results


def classify_and_dedupe(families: list[QueryFamilyResult]) -> list[Citation]:
    all_citations = [c for family in families for c in family.citations]
    deduped = deduplicate_citations(all_citations)
    for citation in deduped:
        citation.raw.setdefault("stance", rule_based_stance(citation.excerpt))
    return deduped
