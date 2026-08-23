"""Load sanitized precomputed public-demo analysis payloads."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline_core.config import PUBLIC_DEMO_BUNDLE_DIR, SYNTHETIC_PATIENTS_DIR

from app.models_orm import AnalysisRun, AnalysisStage


SANITIZE_DROP_KEYS = {"expression", "expression_snapshot", "ground_truth"}


def bundle_manifest() -> dict:
    path = PUBLIC_DEMO_BUNDLE_DIR / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def bundle_ready() -> bool:
    manifest = bundle_manifest()
    patients = manifest.get("patients") or []
    return bool(patients) and all((PUBLIC_DEMO_BUNDLE_DIR / f"{item}.json").exists() for item in patients)


def _sanitize(payload: dict) -> dict:
    out = dict(payload)
    for key in SANITIZE_DROP_KEYS:
        out.pop(key, None)
    return out


def load_bundle_payload(synthetic_id: str) -> dict:
    path = PUBLIC_DEMO_BUNDLE_DIR / f"{synthetic_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Public demo bundle missing for {synthetic_id}. Run jobs/build_public_demo_bundle.py."
        )
    return _sanitize(json.loads(path.read_text()))


def apply_bundle_to_run(run: AnalysisRun, synthetic_id: str) -> AnalysisRun:
    bundle = load_bundle_payload(synthetic_id)
    result = bundle.get("result") or bundle
    run.patient_label = synthetic_id
    run.patient_metadata = result.get("patient_metadata") or bundle.get("patient_metadata") or {}
    run.administered_regimen = result.get("administered_regimen") or bundle.get("administered_regimen") or []
    run.result_payload = result
    run.status = "completed"
    run.current_stage = "assemble"
    run.cluster_probabilities = (result.get("cluster_prediction") or {}).get("probabilities")
    run.confidence_level = (result.get("cluster_prediction") or {}).get("confidence_level")
    run.gene_coverage = (result.get("cluster_prediction") or {}).get("gene_coverage")
    run.expression_snapshot = None
    run.classifier_method = (result.get("cluster_prediction") or {}).get("method_used")
    return run


def bundle_stage_rows(run_id: str) -> list[AnalysisStage]:
    labels = [
        ("validate", "Validating profile"),
        ("deconvolve", "Estimating tumour composition"),
        ("encode_latent", "Encoding latent position"),
        ("infer_activity", "Inferring pathway and TF activity"),
        ("project_sensitivity", "Projecting drug-pathway sensitivity"),
        ("calibrate_set", "Calibrating the prediction set"),
        ("assemble", "Preparing dashboard"),
    ]
    return [
        AnalysisStage(run_id=run_id, stage_id=stage_id, label=label, status="completed")
        for stage_id, label in labels
    ]


def synthetic_ids_from_index() -> list[str]:
    index_path = SYNTHETIC_PATIENTS_DIR / "index.json"
    if not index_path.exists():
        return []
    return [item["synthetic_id"] for item in json.loads(index_path.read_text())]


def write_bundle_payload(synthetic_id: str, result: dict, extra: dict | None = None) -> Path:
    PUBLIC_DEMO_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "synthetic_id": synthetic_id,
        "result": _sanitize(result),
        **(extra or {}),
    }
    path = PUBLIC_DEMO_BUNDLE_DIR / f"{synthetic_id}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path
