from app.services.v2_prototype import is_demo_patient, list_demo_patients, load_demo_payload


def test_demo_patients_are_the_three_held_out_ids():
    ids = {row["patient_id"] for row in list_demo_patients()}
    assert ids == {"TCGA-A8-A081", "TCGA-OK-A5Q2", "TCGA-A1-A0SK"}
    assert is_demo_patient("TCGA-A8-A081")
    assert not is_demo_patient("SYN-HIG-001")


def test_abstain_patient_has_no_candidates_or_prognostic_panel():
    payload = load_demo_payload("TCGA-A1-A0SK")
    assert payload["state"] == 3
    assert payload["abstention"]["abstained"] is True
    assert payload.get("pathway_candidates") is None
    assert payload.get("prognostic_estimate") is None
    assert "pathway_candidates" not in payload["abstention"]["sections_rendered"]


def test_candidates_are_unvalidated_pathway_filter():
    full = load_demo_payload("TCGA-A8-A081")
    missing = load_demo_payload("TCGA-OK-A5Q2")
    assert full["state"] == 1
    assert missing["state"] == 2
    for payload in (full, missing):
        cand = payload["pathway_candidates"]
        assert cand["basis"] == "pathway_activity_threshold"
        assert cand["validated"] is False
        assert "coverage_level" not in cand
    full_w = full["position"]["posterior_width"]
    missing_w = missing["position"]["posterior_width"]
    assert missing_w > full_w
    meth = next(row for row in missing["modality_value_estimate"] if row["modality"] == "methylation")
    assert meth["present"] is False
    assert meth["posterior_width_reduction"] != 0.41
