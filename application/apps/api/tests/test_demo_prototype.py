from app.services.v2_prototype import is_demo_patient, list_demo_patients, load_demo_payload


def test_demo_patients_are_the_three_held_out_ids():
    ids = {row["patient_id"] for row in list_demo_patients()}
    assert ids == {"TCGA-A8-A081", "TCGA-OK-A5Q2", "TCGA-A1-A0SK"}
    assert is_demo_patient("TCGA-A8-A081")
    assert not is_demo_patient("SYN-HIG-001")


def test_abstain_patient_has_no_prediction_set():
    payload = load_demo_payload("TCGA-A1-A0SK")
    assert payload["state"] == 3
    assert payload["abstention"]["abstained"] is True
    assert payload["prediction_set"] is None
    assert "prediction_set" not in payload["abstention"]["sections_rendered"]


def test_missing_view_set_is_wider_than_full_modality():
    full = load_demo_payload("TCGA-A8-A081")
    missing = load_demo_payload("TCGA-OK-A5Q2")
    assert full["state"] == 1
    assert missing["state"] == 2
    assert len(missing["prediction_set"]["set_members"]) > len(full["prediction_set"]["set_members"])
