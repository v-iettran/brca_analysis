"""Public-demo synthetic-only contracts, sessions, and bundle loading."""

from __future__ import annotations

import json

import pytest

from app.config import get_settings
from app.middleware.rate_limit import reset_rate_limits
from pipeline_core.config import PUBLIC_DEMO_BUNDLE_DIR
from pipeline_core.display_gating import apply_display_gating
from pipeline_core.safety import check_safety


def _write_bundle(synthetic_id: str) -> None:
    PUBLIC_DEMO_BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    paclitaxel = {
        "drug": "paclitaxel",
        "canonical": "paclitaxel",
        "list1_percentile": 0.91,
        "list2_percentile": 0.84,
        "weaker_percentile": 0.84,
        "list1_rank": 4,
        "list2_rank": 7,
        "targets": ["TUBB"],
        "is_in_administered_regimen": True,
        "nomination_rank": 1,
        "robustness": {},
    }
    gated = apply_display_gating([paclitaxel])
    payload = {
        "synthetic_id": synthetic_id,
        "result": {
            "schema_version": "v2",
            "patient_metadata": {"er_status": "Positive"},
            "administered_regimen": ["paclitaxel"],
            "cluster_prediction": {
                "probabilities": {"2": 0.82},
                "top_cluster": 2,
                "top_probability": 0.82,
                "confidence_level": "high",
                "gene_coverage": 0.94,
                "genes_found": 180,
                "genes_requested": 200,
                "method_used": "signature_similarity",
                "warnings": [],
            },
            "overlap_nominations": gated["visible"],
            "overlap_exploratory": gated["exploratory"],
            "overlap_technical_excluded": gated["technical_excluded"],
            "display_gate_summary": gated["gate_summary"],
            "compound_registry_version": gated["registry_version"],
            "analysis_summary": {
                "top_cluster": 2,
                "top_probability": 0.82,
                "confidence_level": "high",
                "headline_nominations": [{"drug": "paclitaxel"}],
                "dominant_uncertainty": "Cluster signatures are one-vs-rest among METABRIC tumours; there is no normal-breast reference.",
            },
            "clinical_comparators": [],
            "predictor_combinations": [],
            "limitations": [
                "Cluster signatures are one-vs-rest among METABRIC tumours; there is no normal-breast reference."
            ],
            "list1_drugs": [{"drug": "paclitaxel", "drug_rank": 4}],
            "list2_drugs": [{"drug": "paclitaxel", "drug_rank": 7}],
        },
    }
    (PUBLIC_DEMO_BUNDLE_DIR / f"{synthetic_id}.json").write_text(json.dumps(payload))
    (PUBLIC_DEMO_BUNDLE_DIR / "manifest.json").write_text(
        json.dumps({"patients": [synthetic_id], "bundle_version": "v1"})
    )


@pytest.fixture
def public_mode(monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("ALLOW_CUSTOM_UPLOADS", "false")
    get_settings.cache_clear()
    reset_rate_limits()
    yield
    get_settings.cache_clear()
    reset_rate_limits()


def test_public_mode_rejects_expression_upload(client, public_mode, real_synthetic_patient):
    response = client.post(
        "/analysis",
        json={
            "patient_label": real_synthetic_patient["synthetic_id"],
            "expression": real_synthetic_patient["expression"],
            "metadata": real_synthetic_patient["metadata"],
            "administered_regimen": real_synthetic_patient["administered_regimen"],
        },
    )
    assert response.status_code == 403
    assert "synthetic" in response.json()["detail"].lower()


def test_public_synthetic_submit_loads_bundle_without_expression(client, public_mode):
    synthetic_id = "SYN-HIG-fae88583"
    _write_bundle(synthetic_id)
    listed = client.get("/patients/synthetic")
    assert listed.status_code == 200
    detail = client.get(f"/patients/synthetic/{synthetic_id}")
    assert detail.status_code == 200
    assert detail.json().get("expression") in (None, {})
    created = client.post(f"/analysis/synthetic/{synthetic_id}")
    assert created.status_code == 200, created.text
    run_id = created.json()["run_id"]
    result = client.get(f"/analysis/{run_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "completed"
    assert "expression" not in (body.get("result") or {})
    assert body["cluster_prediction"]["top_cluster"] == 2
    recalc = client.post(f"/analysis/{run_id}/recalculate", json={"top_up": 50, "top_down": 50})
    assert recalc.status_code == 403


def test_public_session_ownership(client, public_mode):
    from fastapi.testclient import TestClient
    from app.main import app

    synthetic_id = "SYN-HIG-fae88583"
    _write_bundle(synthetic_id)
    first = TestClient(app)
    created = first.post(f"/analysis/synthetic/{synthetic_id}")
    run_id = created.json()["run_id"]
    assert first.get(f"/analysis/{run_id}").status_code == 200
    outsider = TestClient(app)
    assert outsider.get(f"/analysis/{run_id}").status_code == 404
    assert check_safety(json.dumps(first.get(f"/analysis/{run_id}").json())) == []
