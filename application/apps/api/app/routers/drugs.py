from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.middleware.rate_limit import limit_general
from app.models_orm import AnalysisRun
from app.services.literature_service import search_literature_for_drug
from app.services.session_service import get_owned_run
from app.services.trials_service import search_trials_for_drug

router = APIRouter(prefix="/analysis/{run_id}/drugs", tags=["drugs"])


def _get_run_and_candidate(
    db: Session, run_id: str, drug: str, request: Request
) -> tuple[AnalysisRun, dict]:
    run = get_owned_run(db, run_id, request)
    payload = run.result_payload or {}
    candidates = (
        payload.get("top_candidate_drugs", [])
        + payload.get("overlap_nominations", [])
        + payload.get("overlap_exploratory", [])
    )
    match = next((c for c in candidates if str(c.get("drug", "")).lower() == drug.lower()), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Drug {drug!r} was not among this run's candidates")
    return run, match


@router.get("/{drug}/literature")
def get_drug_literature(run_id: str, drug: str, request: Request, db: Session = Depends(get_db)) -> dict:
    limit_general(request)
    _run, candidate = _get_run_and_candidate(db, run_id, drug, request)
    targets = candidate.get("targets", [])
    return search_literature_for_drug(db, drug, targets)


@router.get("/{drug}/trials")
def get_drug_trials(run_id: str, drug: str, request: Request, db: Session = Depends(get_db)) -> dict:
    limit_general(request)
    run, _candidate = _get_run_and_candidate(db, run_id, drug, request)
    return search_trials_for_drug(db, drug, run.patient_metadata or {})
