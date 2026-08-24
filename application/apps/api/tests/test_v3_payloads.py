from app.services.v3_prototype import load_v3_bundle


def test_v3_bundle_splits_cohort_and_patient_and_state3_omits_therapy():
    cohort, patient = load_v3_bundle("TCGA-A1-A0SK")
    assert cohort is not None and patient is not None
    assert cohort["schema_version"] == "v3_cluster"
    assert "configurations" in cohort
    preg = next(c for c in cohort["configurations"].values() if not c["exploratory"])
    assert preg["km"]["os"]["p_value"] is not None
    exploratory = next(c for c in cohort["configurations"].values() if c["exploratory"])
    assert exploratory["km"]["os"]["p_value"] is None
    assert patient["state"] == 3
    assert patient["reversal_candidates"] is None
    assert patient["prognostic_estimate"] is None
    assert patient["nearest_lines"] is None


def test_unknown_patient_does_not_invent_a_payload():
    cohort, patient = load_v3_bundle("NOT-A-PATIENT")
    assert cohort is not None
    assert patient is None
