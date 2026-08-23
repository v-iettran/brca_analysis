import json

from pipeline_core.safety import check_safety


def _submit(client, patient: dict) -> dict:
    payload = {
        "patient_label": patient["synthetic_id"],
        "expression": patient["expression"],
        "metadata": patient["metadata"],
        "administered_regimen": patient["administered_regimen"],
    }
    response = client.post("/analysis", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_submit_analysis_high_confidence_patient(client, real_synthetic_patient):
    result = _submit(client, real_synthetic_patient)
    assert result["status"] == "completed"
    assert result["patient_metadata"]["er_status"] == real_synthetic_patient["metadata"]["er_status"]
    cluster = result["cluster_prediction"]
    assert abs(sum(cluster["probabilities"].values()) - 1.0) < 1e-6
    assert cluster["confidence_level"] in {"high", "moderate", "low", "abstain"}
    assert len(result["top_candidate_drugs"]) > 0

    pcr = result["administered_regimen_pcr"]
    assert pcr["applicability_gate"]["represented"] is True

    # Full response, serialized, must never contain banned evidence-language phrases.
    assert check_safety(json.dumps(result)) == []


def test_submit_analysis_low_quality_patient_flags_low_confidence(client, low_quality_synthetic_patient):
    result = _submit(client, low_quality_synthetic_patient)
    assert result["status"] == "completed"
    cluster = result["cluster_prediction"]
    assert cluster["gene_coverage"] < 0.5
    assert cluster["confidence_level"] in {"moderate", "low", "abstain"} or len(result["warnings"]) > 0


def test_get_analysis_round_trip(client, real_synthetic_patient):
    submitted = _submit(client, real_synthetic_patient)
    response = client.get(f"/analysis/{submitted['run_id']}")
    assert response.status_code == 200
    fetched = response.json()
    assert fetched["run_id"] == submitted["run_id"]
    assert fetched["cluster_prediction"]["top_cluster"] == submitted["cluster_prediction"]["top_cluster"]


def test_get_analysis_unknown_run_id_404(client):
    response = client.get("/analysis/does-not-exist")
    assert response.status_code == 404


def test_get_analysis_audit_trail(client, real_synthetic_patient):
    submitted = _submit(client, real_synthetic_patient)
    response = client.get(f"/analysis/{submitted['run_id']}/audit")
    assert response.status_code == 200
    events = response.json()
    tool_names = {e["tool_name"] for e in events}
    assert {"validate_patient", "score_clusters", "nominate_overlap", "prefetch_literature"}.issubset(tool_names)


def test_submit_analysis_rejects_empty_expression(client):
    payload = {"patient_label": "SYN-EMPTY", "expression": {}, "administered_regimen": []}
    response = client.post("/analysis", json=payload)
    assert response.status_code == 422
