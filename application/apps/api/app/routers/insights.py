from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.middleware.rate_limit import limit_general, limit_llm
from app.models_orm import AuditEvent, ChatMessage
from app.schemas.chat import CopilotChatRequest, CopilotChatResponse
from app.schemas.cluster import ClusterDetailOut
from app.schemas.rationale import GroundedRationaleResponse
from app.services.cluster_service import cluster_contains_gene, cluster_detail
from app.services.copilot_service import answer_copilot_question
from app.services.literature_service import search_literature_for_gene
from app.services.rationale_service import build_rationale
from app.services.session_service import get_owned_run
from app.services.trials_service import search_trials_for_run

router = APIRouter(prefix="/analysis/{run_id}", tags=["analysis insights"])


@router.get("/clusters/{cluster_id}", response_model=ClusterDetailOut)
def get_cluster_detail(
    run_id: str,
    cluster_id: int,
    request: Request,
    top_n: int = Query(default=12, ge=5, le=150),
    db: Session = Depends(get_db),
) -> ClusterDetailOut:
    limit_general(request)
    run = get_owned_run(db, run_id, request)
    probabilities = run.cluster_probabilities or {}
    if str(cluster_id) not in probabilities:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} is not present in this run")
    try:
        detail = cluster_detail(cluster_id, float(probabilities[str(cluster_id)]), top_n)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ClusterDetailOut.model_validate(detail)


@router.get("/clusters/{cluster_id}/genes/{gene}/literature")
def get_cluster_gene_literature(
    run_id: str,
    cluster_id: int,
    gene: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    limit_general(request)
    get_owned_run(db, run_id, request)
    try:
        present = cluster_contains_gene(cluster_id, gene)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not present:
        raise HTTPException(
            status_code=404,
            detail=f"Gene {gene!r} is not present in the committed signature for cluster {cluster_id}",
        )
    return search_literature_for_gene(db, gene, cluster_id)


@router.get("/trials")
def get_run_trials(run_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    limit_general(request)
    run = get_owned_run(db, run_id, request)
    return search_trials_for_run(db, run)


@router.get("/rationale", response_model=GroundedRationaleResponse)
def get_run_rationale(
    run_id: str,
    request: Request,
    selected_drug: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> GroundedRationaleResponse:
    limit_general(request)
    limit_llm(request)
    run = get_owned_run(db, run_id, request)
    started = time.perf_counter()
    rationale = build_rationale(
        run,
        "Summarize the validated evidence for the selected research nomination.",
        selected_drug,
    )
    db.add(
        AuditEvent(
            run_id=run_id,
            tool_name="grounded_rationale",
            input_summary={"selected_drug": selected_drug},
            output_summary={
                "provider": rationale.provider,
                "model": rationale.model,
                "fallback_used": rationale.fallback_used,
            },
            duration_ms=(time.perf_counter() - started) * 1000,
        )
    )
    db.commit()
    return rationale


@router.get("/chat")
def get_chat_history(run_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    limit_general(request)
    run = get_owned_run(db, run_id, request)
    messages = sorted(run.chat_messages, key=lambda m: m.created_at)
    return {
        "run_id": run_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": m.sources or [],
                "active_view": m.active_view,
                "used_local_model": m.used_local_model,
                "rationale": m.rationale,
                "provider": m.llm_provider,
                "model": m.llm_model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.post("/chat", response_model=CopilotChatResponse)
def chat_with_copilot(
    run_id: str,
    body: CopilotChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> CopilotChatResponse:
    limit_general(request)
    limit_llm(request)
    run = get_owned_run(db, run_id, request)
    started = time.perf_counter()
    if not body.history and run.chat_messages:
        from app.schemas.chat import ChatHistoryMessage

        body.history = [
            ChatHistoryMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
            for m in sorted(run.chat_messages, key=lambda x: x.created_at)[-8:]
            if m.role in {"user", "assistant"}
        ]
    response = CopilotChatResponse.model_validate(answer_copilot_question(run, body))
    db.add(
        ChatMessage(
            run_id=run_id,
            role="user",
            content=body.message,
            active_view=body.active_view,
        )
    )
    db.add(
        ChatMessage(
            run_id=run_id,
            role="assistant",
            content=response.answer,
            sources=[s.model_dump() for s in response.sources],
            active_view=body.active_view,
            used_local_model=response.used_local_model,
            rationale=response.rationale.model_dump() if response.rationale else None,
            llm_provider=response.provider,
            llm_model=response.model,
        )
    )
    db.add(
        AuditEvent(
            run_id=run_id,
            tool_name="copilot_explain_run_evidence",
            input_summary={
                "message_length": len(body.message),
                "selected_drug": body.selected_drug,
                "selected_cluster": body.selected_cluster,
                "active_view": body.active_view,
            },
            output_summary={
                "used_local_model": response.used_local_model,
                "provider": response.provider,
                "model": response.model,
                "source_sections": [source.section for source in response.sources],
            },
            duration_ms=(time.perf_counter() - started) * 1000,
        )
    )
    db.commit()
    return response
