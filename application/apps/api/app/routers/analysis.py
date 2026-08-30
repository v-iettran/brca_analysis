from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.middleware.rate_limit import limit_analysis, limit_general
from app.models_orm import AnalysisRun
from app.schemas.patient import PatientProfileIn, RecalculateRequest
from app.schemas.run import (
    AnalysisProgressOut,
    AnalysisResultOut,
    AnalysisStageOut,
    AnalysisSubmitAck,
    AuditEventOut,
    WarningOut,
)
from app.services.analysis_service import (
    materialize_public_synthetic_run,
    recalculate_signatures,
    run_analysis,
    start_analysis_async,
    start_demo_analysis,
)
from app.services.v2_prototype import is_demo_patient
from app.services.demo_guard import assert_synthetic_only_submission, load_synthetic_profile, public_uploads_blocked
from app.services.v3_prototype import load_v3_bundle
from app.services.session_service import get_or_create_session, get_owned_run

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _to_result_out(run: AnalysisRun) -> AnalysisResultOut:
    payload = run.result_payload or {}
    stored_patient = payload.get("v3_patient") or {}
    v3_cohort = payload.get("v3_cohort")
    v3_patient = stored_patient or None
    patient_id = str(stored_patient.get("patient_id") or payload.get("patient_id") or "")
    if patient_id:
        current_cohort, current_patient = load_v3_bundle(patient_id)
        if current_cohort:
            v3_cohort = current_cohort
        if current_patient:
            v3_patient = current_patient

    return AnalysisResultOut(
        run_id=run.run_id,
        status=run.status,  # type: ignore[arg-type]
        created_at=run.created_at,
        patient_label=run.patient_label,
        patient_metadata=run.patient_metadata or {},
        administered_regimen=run.administered_regimen or [],
        revision=int(run.revision or 0),
        signature_params=payload.get("signature_params"),
        cluster_prediction=payload.get("cluster_prediction"),
        rna_projection=payload.get("rna_projection"),
        cluster_signature=payload.get("cluster_signature"),
        residual_signature=payload.get("residual_signature"),
        overlap_nominations=payload.get("overlap_nominations", []),
        overlap_exploratory=payload.get("overlap_exploratory", []),
        overlap_technical_excluded=payload.get("overlap_technical_excluded", []),
        display_gate_summary=payload.get("display_gate_summary"),
        compound_registry_version=payload.get("compound_registry_version"),
        analysis_summary=payload.get("analysis_summary"),
        clinical_comparators=payload.get("clinical_comparators", []),
        predictor_single_drugs=payload.get("predictor_single_drugs", []),
        predictor_combinations=payload.get("predictor_combinations", []),
        predictor_summary=payload.get("predictor_summary"),
        near_consensus=payload.get("near_consensus", []),
        overlap_summary=payload.get("overlap_summary"),
        almanac_combinations=payload.get("almanac_combinations", []),
        list1_drugs=payload.get("list1_drugs", []),
        list2_drugs=payload.get("list2_drugs", []),
        administered_regimen_pcr=payload.get("administered_regimen_pcr"),
        top_candidate_drugs=payload.get("top_candidate_drugs", []),
        limitations=payload.get("limitations", []),
        warnings=[WarningOut(severity=w.severity, message=w.message) for w in run.warnings],
        error_message=run.error_message,
        current_stage=run.current_stage,
        prototype=payload.get("prototype"),
        # Read the v3 bundle from disk rather than from the run's snapshot.
        # The cohort and the demo patient payloads are shared, versioned
        # artifacts, not per-run output: freezing them at submission meant every
        # link created before a pipeline rerun kept serving the old cohort for
        # ever, with no way for a reader to tell.
        v3_cohort=v3_cohort,
        v3_patient=v3_patient,
        schema_version=payload.get("schema_version"),
        s4_ships=bool(payload.get("s4_ships")),
    )


@router.post("", response_model=AnalysisResultOut)
def submit_analysis(
    profile: PatientProfileIn,
    request: Request,
    response: Response,
    async_mode: bool = Query(False, alias="async"),
    db: Session = Depends(get_db),
):
    limit_general(request)
    limit_analysis(request)
    assert_synthetic_only_submission()
    session_id = get_or_create_session(request, response)
    try:
        if async_mode:
            run_id = start_analysis_async(
                profile, top_up=profile.top_up, top_down=profile.top_down, session_id=session_id
            )
            run = db.get(AnalysisRun, run_id)
            return _to_result_out(run)
        run = run_analysis(db, profile, top_up=profile.top_up, top_down=profile.top_down, session_id=session_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"A required scientific artifact is missing: {exc}. Run the jobs/ scripts first.",
        ) from exc
    return _to_result_out(run)


@router.post("/async", response_model=AnalysisSubmitAck)
def submit_analysis_async(
    profile: PatientProfileIn, request: Request, response: Response
) -> AnalysisSubmitAck:
    limit_general(request)
    limit_analysis(request)
    assert_synthetic_only_submission()
    session_id = get_or_create_session(request, response)
    run_id = start_analysis_async(
        profile, top_up=profile.top_up, top_down=profile.top_down, session_id=session_id
    )
    return AnalysisSubmitAck(run_id=run_id, status="pending", poll_url=f"/analysis/{run_id}/progress")


@router.post("/demo/{patient_id}", response_model=AnalysisSubmitAck)
def submit_demo_analysis(
    patient_id: str, request: Request, response: Response
) -> AnalysisSubmitAck:
    limit_general(request)
    limit_analysis(request)
    if not is_demo_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Unknown demo patient {patient_id!r}")
    session_id = get_or_create_session(request, response)
    run_id = start_demo_analysis(patient_id, session_id=session_id)
    return AnalysisSubmitAck(run_id=run_id, status="pending", poll_url=f"/analysis/{run_id}/progress")


@router.post("/synthetic/{synthetic_id}", response_model=AnalysisSubmitAck)
def submit_synthetic_analysis(
    synthetic_id: str, request: Request, response: Response, db: Session = Depends(get_db)
) -> AnalysisSubmitAck:
    limit_general(request)
    limit_analysis(request)
    session_id = get_or_create_session(request, response)
    try:
        if public_uploads_blocked():
            run = materialize_public_synthetic_run(db, synthetic_id, session_id=session_id)
            return AnalysisSubmitAck(
                run_id=run.run_id, status=run.status, poll_url=f"/analysis/{run.run_id}/progress"
            )
        profile = load_synthetic_profile(synthetic_id)
        run_id = start_analysis_async(profile, session_id=session_id)
        return AnalysisSubmitAck(run_id=run_id, status="pending", poll_url=f"/analysis/{run_id}/progress")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=AnalysisResultOut)
def get_analysis(run_id: str, request: Request, db: Session = Depends(get_db)) -> AnalysisResultOut:
    return _to_result_out(get_owned_run(db, run_id, request))


@router.get("/{run_id}/progress", response_model=AnalysisProgressOut)
def get_analysis_progress(run_id: str, request: Request, db: Session = Depends(get_db)) -> AnalysisProgressOut:
    run = get_owned_run(db, run_id, request)
    stages = [
        AnalysisStageOut(
            stage_id=s.stage_id,
            label=s.label,
            status=s.status,  # type: ignore[arg-type]
            detail=s.detail,
            created_at=s.created_at,
        )
        for s in sorted(run.stages, key=lambda x: x.created_at)
    ]
    return AnalysisProgressOut(
        run_id=run.run_id,
        status=run.status,  # type: ignore[arg-type]
        current_stage=run.current_stage,
        stages=stages,
        error_message=run.error_message,
    )


@router.post("/{run_id}/recalculate", response_model=AnalysisResultOut)
def recalculate_analysis(
    run_id: str, body: RecalculateRequest, request: Request, db: Session = Depends(get_db)
) -> AnalysisResultOut:
    if public_uploads_blocked():
        raise HTTPException(status_code=403, detail="Recalculation is disabled in public demo mode.")
    run = get_owned_run(db, run_id, request)
    try:
        run = recalculate_signatures(db, run, body.top_up, body.top_down)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _to_result_out(run)


@router.get("/{run_id}/audit", response_model=list[AuditEventOut])
def get_analysis_audit(run_id: str, request: Request, db: Session = Depends(get_db)) -> list[AuditEventOut]:
    run = get_owned_run(db, run_id, request)
    return [
        AuditEventOut(
            tool_name=e.tool_name,
            input_summary=e.input_summary,
            output_summary=e.output_summary,
            duration_ms=e.duration_ms,
            created_at=e.created_at,
        )
        for e in run.audit_events
    ]
