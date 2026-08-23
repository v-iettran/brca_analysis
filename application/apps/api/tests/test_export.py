import csv
import io
import json


def _submit(client, patient: dict) -> str:
    payload = {
        "patient_label": patient["synthetic_id"],
        "expression": patient["expression"],
        "metadata": patient["metadata"],
        "administered_regimen": patient["administered_regimen"],
    }
    result = client.post("/analysis", json=payload).json()
    return result["run_id"]


def test_export_json(client, real_synthetic_patient):
    run_id = _submit(client, real_synthetic_patient)
    response = client.get(f"/analysis/{run_id}/export/json")
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["run_id"] == run_id
    assert "banner" in body and "not a clinical" in body["banner"].lower()


def test_export_csv(client, real_synthetic_patient):
    run_id = _submit(client, real_synthetic_patient)
    response = client.get(f"/analysis/{run_id}/export/csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    assert len(rows) > 0
    assert "drug" in rows[0]


def test_export_pdf(client, real_synthetic_patient):
    run_id = _submit(client, real_synthetic_patient)
    response = client.get(f"/analysis/{run_id}/export/pdf")
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_export_unsupported_format(client, real_synthetic_patient):
    run_id = _submit(client, real_synthetic_patient)
    response = client.get(f"/analysis/{run_id}/export/xml")
    assert response.status_code == 400


def test_export_unknown_run(client):
    response = client.get("/analysis/does-not-exist/export/json")
    assert response.status_code == 404
