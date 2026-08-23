"""Synthetic demonstration patients.

Public demo mode never returns expression vectors.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from pipeline_core.config import SYNTHETIC_PATIENTS_DIR

from app.services.demo_guard import list_synthetic_index, public_uploads_blocked
from app.services.v2_prototype import list_demo_patients, load_demo_payload, load_glossary
from app.schemas.prototype import DemoPatientSummary

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/demo", response_model=list[DemoPatientSummary])
def list_held_out_demo_patients() -> list[DemoPatientSummary]:
    return [DemoPatientSummary.model_validate(row) for row in list_demo_patients()]


@router.get("/demo/{patient_id}")
def get_held_out_demo_patient(patient_id: str) -> dict:
    try:
        payload = load_demo_payload(patient_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "patient_id": payload["patient_id"],
        "role": payload["role"],
        "title": payload.get("title"),
        "description": payload.get("description"),
        "metadata": payload.get("patient_metadata") or {},
        "expression_omitted": True,
    }


@router.get("/glossary")
def get_glossary() -> dict:
    return load_glossary()


@router.get("/synthetic")
def list_synthetic_patients() -> list[dict]:
    return list_synthetic_index()


@router.get("/synthetic/{synthetic_id}")
def get_synthetic_patient(synthetic_id: str) -> dict:
    summaries = {item["synthetic_id"]: item for item in list_synthetic_index()}
    if synthetic_id not in summaries:
        raise HTTPException(status_code=404, detail=f"Unknown synthetic patient id {synthetic_id!r}")
    if public_uploads_blocked():
        return {**summaries[synthetic_id], "expression": None, "expression_omitted": True}
    path = SYNTHETIC_PATIENTS_DIR / f"{synthetic_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Unknown synthetic patient id {synthetic_id!r}")
    data = json.loads(path.read_text())
    data.pop("ground_truth", None)
    return data
