def test_list_synthetic_patients(client):
    response = client.get("/patients/synthetic")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    scenarios = {p["scenario"] for p in body}
    assert scenarios == {"high_confidence", "mixed_cluster", "low_quality"}
    for patient in body:
        assert "ground_truth" not in patient


def test_get_synthetic_patient_strips_ground_truth(client, real_synthetic_patient):
    synthetic_id = real_synthetic_patient["synthetic_id"]
    response = client.get(f"/patients/synthetic/{synthetic_id}")
    assert response.status_code == 200
    body = response.json()
    assert "ground_truth" not in body
    assert body["synthetic_id"] == synthetic_id
    assert len(body["expression"]) > 0


def test_get_unknown_synthetic_patient_404(client):
    response = client.get("/patients/synthetic/SYN-DOES-NOT-EXIST")
    assert response.status_code == 404
