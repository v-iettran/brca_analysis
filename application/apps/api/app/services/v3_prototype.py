"""Load v3 cohort/patient payloads for demo analyses."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _cohort() -> dict | None:
    for path in (DATA_DIR / "v3" / "cohort_payload.json", DATA_DIR / "v3" / "demo_payloads_v3.json"):
        if not path.exists():
            continue
        obj = json.loads(path.read_text())
        if "cohort" in obj:
            return obj["cohort"]
        return obj
    return None


def _patients() -> dict:
    combined = DATA_DIR / "v3" / "demo_payloads_v3.json"
    if combined.exists():
        obj = json.loads(combined.read_text())
        if isinstance(obj.get("patients"), dict):
            return obj["patients"]
    out = {}
    folder = DATA_DIR / "v3"
    if folder.is_dir():
        for path in folder.glob("payload_*.json"):
            payload = json.loads(path.read_text())
            out[payload["patient_id"]] = payload
    return out


def load_v3_bundle(patient_id: str) -> tuple[dict | None, dict | None]:
    cohort = _cohort()
    patients = _patients()
    if patient_id in patients:
        return cohort, patients[patient_id]
    prefix = patient_id[:12]
    for key, row in patients.items():
        if key[:12] == prefix:
            return cohort, row
    return cohort, None
