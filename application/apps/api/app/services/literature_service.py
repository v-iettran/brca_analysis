"""Paperclip literature retrieval with SQLite caching and Ollama-assisted
stance classification for excerpts the rule-based pass leaves "unclear"."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time

from sqlalchemy.orm import Session

from app.adapters.ollama_client import classify_stance_with_llm
from app.adapters.paperclip_client import (
    build_gene_query_families,
    build_query_families,
    classify_and_dedupe,
    get_paperclip_client,
    search_drug_literature,
    search_gene_literature,
)
from app.config import get_settings
from app.models_orm import ExternalQueryCache

settings = get_settings()


def _cache_key(drug: str, targets: list[str]) -> str:
    payload = json.dumps({"version": 2, "drug": drug, "targets": sorted(targets)}, sort_keys=True)
    return "paperclip:" + hashlib.sha256(payload.encode()).hexdigest()


def _gene_cache_key(gene: str) -> str:
    return "paperclip:gene:v2:" + hashlib.sha256(gene.strip().upper().encode()).hexdigest()


def _is_fresh(fetched_at: dt.datetime) -> bool:
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=dt.timezone.utc)
    age = dt.datetime.now(dt.timezone.utc) - fetched_at
    return age < dt.timedelta(hours=settings.external_query_cache_ttl_hours)


def _rank_citations(citations, subject: str, context_terms: list[str]) -> list:
    """Attach transparent metadata-quality and text-relevance scores."""
    subject_lower = subject.lower()
    context_lower = [term.lower() for term in context_terms if term]
    now_year = dt.datetime.now(dt.timezone.utc).year
    for citation in citations:
        text = f"{citation.title or ''} {citation.excerpt or ''}".lower()
        credibility = 10
        credibility += 30 if citation.peer_reviewed is True else 0
        credibility += 20 if citation.doi or citation.pmid or citation.pmcid else 0
        credibility += 10 if citation.journal else 0
        credibility += 10 if citation.full_text_available is True or citation.pmcid else 0
        article_type = (citation.article_type or "").lower()
        credibility += 15 if "review" in article_type or "meta" in article_type else 0
        credibility += 5 if citation.year and now_year - citation.year <= 10 else 0

        matched_queries = citation.raw.get("matched_queries", [])
        relevance = 15
        relevance += 30 if subject_lower in text else 0
        relevance += 25 if "breast cancer" in text or "breast neoplasm" in text else 0
        relevance += min(15, len(matched_queries) * 5)
        relevance += min(15, sum(1 for term in context_lower if term in text) * 5)

        credibility = min(100, credibility)
        relevance = min(100, relevance)
        citation.raw["credibility_score"] = credibility
        citation.raw["relevance_score"] = relevance
        citation.raw["combined_score"] = round(0.45 * credibility + 0.55 * relevance, 1)
        citation.raw["ranking_explanation"] = (
            "Credibility uses publication identifiers, peer-review/full-text metadata, "
            "article type, journal, and recency. Relevance uses subject/context terms "
            "and the number of query families that retrieved the paper."
        )
    citations.sort(key=lambda item: item.raw["combined_score"], reverse=True)
    for rank, citation in enumerate(citations, start=1):
        citation.raw["evidence_rank"] = rank
    return citations


def search_literature_for_drug(
    db: Session, drug: str, targets: list[str], *, use_llm_stance: bool = True
) -> dict:
    cache_key = _cache_key(drug, targets)
    cached = db.get(ExternalQueryCache, cache_key)
    if cached and _is_fresh(cached.fetched_at):
        result = dict(cached.response_json)
        result["cache_hit"] = True
        return result

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if not settings.allow_external_queries:
        return {
            "drug": drug,
            "query_families": [],
            "citations": [],
            "deduplicated_count": 0,
            "raw_result_count": 0,
            "cache_hit": False,
            "searched_at": now,
            "unavailable_reason": "External queries are disabled (ALLOW_EXTERNAL_QUERIES=false).",
        }

    client = get_paperclip_client()
    if client is None:
        return {
            "drug": drug,
            "query_families": [
                {"label": label, "query_text": text, "result_count": 0, "executed_at": now}
                for label, text in build_query_families(drug, targets)
            ],
            "citations": [],
            "deduplicated_count": 0,
            "raw_result_count": 0,
            "cache_hit": False,
            "searched_at": now,
            "unavailable_reason": (
                "Paperclip SDK is not installed or PAPERCLIP_API_KEY is not set. "
                "Install `gxl-paperclip` and set PAPERCLIP_API_KEY to enable literature search."
            ),
        }

    families = search_drug_literature(client, drug, targets)
    citations = classify_and_dedupe(families)
    citations = _rank_citations(citations, drug, ["breast cancer", *targets])

    for citation in citations:
        if (
            use_llm_stance
            and citation.raw.get("stance") == "unclear"
            and settings.ollama_enabled
        ):
            llm_stance = classify_stance_with_llm(settings.ollama_host, settings.ollama_model, citation.excerpt or "")
            if llm_stance:
                citation.raw["stance"] = llm_stance
                citation.raw["stance_source"] = "ollama"
        citation.raw.setdefault("stance_source", "rule_based")

    result = {
        "drug": drug,
        "query_families": [
            {
                "label": f.label,
                "query_text": f.query_text,
                "result_count": f.result_count,
                "executed_at": now,
            }
            for f in families
        ],
        "citations": [
            {
                "title": c.title,
                "year": c.year,
                "doi": c.doi,
                "pmid": c.pmid,
                "pmcid": c.pmcid,
                "journal": c.journal,
                "publisher": c.publisher,
                "source": c.source,
                "article_type": c.article_type,
                "peer_reviewed": c.peer_reviewed,
                "full_text_available": c.full_text_available,
                "excerpt": c.excerpt,
                "stance": c.raw.get("stance", "unclear"),
                "matched_queries": c.raw.get("matched_queries", []),
                "credibility_score": c.raw.get("credibility_score"),
                "relevance_score": c.raw.get("relevance_score"),
                "combined_score": c.raw.get("combined_score"),
                "evidence_rank": c.raw.get("evidence_rank"),
                "ranking_explanation": c.raw.get("ranking_explanation"),
            }
            for c in citations
        ],
        "deduplicated_count": len(citations),
        "raw_result_count": sum(f.result_count for f in families),
        "cache_hit": False,
        "searched_at": now,
    }

    db.merge(
        ExternalQueryCache(
            cache_key=cache_key,
            service="paperclip",
            query_text=f"drug={drug}; targets={targets}",
            response_json=result,
        )
    )
    db.commit()
    return result


def search_literature_for_gene(
    db: Session, gene: str, cluster_id: int, *, use_llm_stance: bool = True
) -> dict:
    """Retrieve literature context for a cluster-signature gene on demand."""
    symbol = gene.strip().upper()
    cache_key = _gene_cache_key(symbol)
    cached = db.get(ExternalQueryCache, cache_key)
    if cached and _is_fresh(cached.fetched_at):
        result = dict(cached.response_json)
        result["cluster_id"] = cluster_id
        result["cache_hit"] = True
        return result

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    empty_result = {
        "gene": symbol,
        "cluster_id": cluster_id,
        "query_families": [
            {"label": label, "query_text": text, "result_count": 0, "executed_at": now}
            for label, text in build_gene_query_families(symbol)
        ],
        "citations": [],
        "deduplicated_count": 0,
        "raw_result_count": 0,
        "cache_hit": False,
        "searched_at": now,
        "interpretation_note": (
            "Publication count provides context only; it does not validate the cluster "
            "coefficient or establish that this gene causes disease or treatment response."
        ),
    }
    if not settings.allow_external_queries:
        return {
            **empty_result,
            "unavailable_reason": "External queries are disabled (ALLOW_EXTERNAL_QUERIES=false).",
        }

    client = get_paperclip_client()
    if client is None:
        return {
            **empty_result,
            "unavailable_reason": (
                "Paperclip SDK is not installed or PAPERCLIP_API_KEY is not set. "
                "Install `gxl-paperclip` and set PAPERCLIP_API_KEY to enable literature search."
            ),
        }

    families = search_gene_literature(client, symbol)
    citations = classify_and_dedupe(families)
    for citation in citations:
        if (
            use_llm_stance
            and citation.raw.get("stance") == "unclear"
            and settings.ollama_enabled
        ):
            llm_stance = classify_stance_with_llm(
                settings.ollama_host, settings.ollama_model, citation.excerpt or ""
            )
            if llm_stance:
                citation.raw["stance"] = llm_stance
    citations = _rank_citations(citations, symbol, ["breast cancer"])

    result = {
        **empty_result,
        "query_families": [
            {
                "label": family.label,
                "query_text": family.query_text,
                "result_count": family.result_count,
                "executed_at": now,
            }
            for family in families
        ],
        "citations": [
            {
                "title": citation.title,
                "year": citation.year,
                "doi": citation.doi,
                "pmid": citation.pmid,
                "pmcid": citation.pmcid,
                "journal": citation.journal,
                "publisher": citation.publisher,
                "source": citation.source,
                "article_type": citation.article_type,
                "peer_reviewed": citation.peer_reviewed,
                "full_text_available": citation.full_text_available,
                "excerpt": citation.excerpt,
                "stance": citation.raw.get("stance", "unclear"),
                "matched_queries": citation.raw.get("matched_queries", []),
                "credibility_score": citation.raw.get("credibility_score"),
                "relevance_score": citation.raw.get("relevance_score"),
                "combined_score": citation.raw.get("combined_score"),
                "evidence_rank": citation.raw.get("evidence_rank"),
                "ranking_explanation": citation.raw.get("ranking_explanation"),
            }
            for citation in citations
        ],
        "deduplicated_count": len(citations),
        "raw_result_count": sum(family.result_count for family in families),
    }
    db.merge(
        ExternalQueryCache(
            cache_key=cache_key,
            service="paperclip",
            query_text=f"gene={symbol}",
            response_json=result,
        )
    )
    db.commit()
    return result


def _summarize_citations(citations: list[dict]) -> dict:
    stance_counts = {"supporting": 0, "conflicting": 0, "neutral": 0, "unclear": 0}
    for citation in citations:
        stance = citation.get("stance") or "unclear"
        if stance not in stance_counts:
            stance = "unclear"
        stance_counts[stance] += 1
    dominant = max(stance_counts, key=stance_counts.get)
    return {
        "retrieved_relevant_references": len(citations),
        "stance_counts": stance_counts,
        "dominant_stance": dominant if citations else None,
        "note": (
            "Counts are retrieved relevant references for the versioned query family, "
            "not total publications or proof of efficacy."
        ),
    }


def prefetch_literature_batch(
    db: Session,
    nominations: list[dict],
    signature_genes: list[str],
    *,
    max_drugs: int = 8,
    max_genes: int = 6,
    budget_seconds: float = 20.0,
) -> dict:
    """Batch-prefetch Paperclip evidence for visible nominations and top genes.

    Literature is optional context. A hung vendor search must not block the
    rest of analysis, so each lookup is fail-open and the batch has a deadline.
    """
    deadline = time.monotonic() + budget_seconds
    drug_summaries: dict[str, dict] = {}
    for row in nominations[:max_drugs]:
        if time.monotonic() >= deadline:
            break
        drug = row.get("drug")
        if not drug:
            continue
        try:
            result = search_literature_for_drug(
                db, drug, row.get("targets") or [], use_llm_stance=False
            )
        except Exception:
            continue
        summary = _summarize_citations(result.get("citations") or [])
        drug_summaries[drug] = {
            **summary,
            "unavailable_reason": result.get("unavailable_reason"),
            "cache_hit": result.get("cache_hit", False),
            "top_citations": (result.get("citations") or [])[:3],
        }

    gene_counts: dict[str, int] = {}
    for gene in signature_genes[:max_genes]:
        if time.monotonic() >= deadline:
            break
        try:
            result = search_literature_for_gene(db, gene, cluster_id=-1, use_llm_stance=False)
        except Exception:
            continue
        gene_counts[gene.upper()] = int(result.get("deduplicated_count") or 0)

    return {"drugs": drug_summaries, "genes": gene_counts}
