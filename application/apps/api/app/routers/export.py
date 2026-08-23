from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.middleware.rate_limit import limit_general
from app.models_orm import ExportRecord
from app.services.report_service import export_csv, export_json, export_pdf
from app.services.session_service import get_owned_run

router = APIRouter(prefix="/analysis/{run_id}/export", tags=["export"])

_EXPORTERS = {"json": export_json, "csv": export_csv, "pdf": export_pdf}
_MEDIA_TYPES = {"json": "application/json", "csv": "text/csv", "pdf": "application/pdf"}


@router.get("/{export_format}")
def export_run(
    run_id: str, export_format: str, request: Request, db: Session = Depends(get_db)
) -> FileResponse:
    limit_general(request)
    if export_format not in _EXPORTERS:
        raise HTTPException(status_code=400, detail=f"Unsupported export format {export_format!r}")

    run = get_owned_run(db, run_id, request)
    if run.status != "completed":
        raise HTTPException(status_code=409, detail=f"Run {run_id} is not completed (status={run.status})")

    path = _EXPORTERS[export_format](run)
    db.add(ExportRecord(run_id=run_id, export_format=export_format, file_path=str(path)))
    db.commit()

    return FileResponse(path=str(path), media_type=_MEDIA_TYPES[export_format], filename=path.name)
