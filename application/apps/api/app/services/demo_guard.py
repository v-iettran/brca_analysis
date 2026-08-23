"""Server-side guards for public-demo synthetic-only operation."""

from __future__ import annotations

import json

from fastapi import HTTPException

from pipeline_core.config import SYNTHETIC_PATIENTS_DIR
from pipeline_core.drug_names import normalize_drug_name

from app.config import get_settings
from app.schemas.patient import PatientMetadata, PatientProfileIn


class PublicDemoForbidden(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=403, detail=detail)


def public_uploads_blocked() -> bool:
    settings = get_settings()
    return settings.public_demo_mode or not settings.allow_custom_uploads


def list_synthetic_index() -> list[dict]:
    index_path = SYNTHETIC_PATIENTS_DIR / "index.json"
    if not index_path.exists():
        raise HTTPException(
            status_code=503,
            detail="No synthetic patients found. Run `python jobs/generate_synthetic_patients.py` first.",
        )
    items = json.loads(index_path.read_text())
    for item in items:
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            item["metadata"] = PatientMetadata.model_validate(metadata).model_dump()
    return items


def load_synthetic_profile(synthetic_id: str) -> PatientProfileIn:
    path = SYNTHETIC_PATIENTS_DIR / f"{synthetic_id}.json"
    if not path.exists():
        known = {item["synthetic_id"] for item in list_synthetic_index()}
        raise HTTPException(
            status_code=404,
            detail=f"Unknown synthetic patient id {synthetic_id!r}. Known: {sorted(known)}",
        )
    data = json.loads(path.read_text())
    data.pop("ground_truth", None)
    return PatientProfileIn(
        patient_label=data["synthetic_id"],
        expression=data["expression"],
        metadata=PatientMetadata.model_validate(data.get("metadata") or {}),
        administered_regimen=[
            normalize_drug_name(item) for item in data.get("administered_regimen") or []
        ],
    )


def assert_synthetic_only_submission() -> None:
    if public_uploads_blocked():
        raise PublicDemoForbidden(
            "Public demo mode accepts only curated synthetic patients. "
            "POST /analysis/synthetic/{synthetic_id} instead of uploading expression."
        )


def assert_synthetic_profile(profile: PatientProfileIn) -> None:
    """Reject browser-supplied expression in public mode."""
    if not public_uploads_blocked():
        return
    raise PublicDemoForbidden(
        "Custom RNA profiles are disabled in public demo mode."
    )
