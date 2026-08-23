"""API tests for V2 staged analysis, recalculation, chat, and exports."""

from __future__ import annotations

import json
import time

from pipeline_core.safety import check_safety


def _submit(client, patient: dict, **extra) -> dict:
    payload = {
        "patient_label": patient["synthetic_id"],
        "expression": patient["expression"],
        "metadata": patient["metadata"],
        "administered_regimen": patient["administered_regimen"],
        **extra,
    }
    response = client.post("/analysis", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_v2_payload_has_overlap_and_signatures(client, real_synthetic_patient):
    result = _submit(client, real_synthetic_patient, top_up=40, top_down=40)
    assert result["status"] == "completed"
    assert result["signature_params"]["top_up"] == 40
    assert result["rna_projection"] is not None
    assert result["cluster_signature"] is not None
    assert result["residual_signature"] is not None
    assert "overlap_nominations" in result
    assert "clinical_comparators" in result
    comparator_names = {row["canonical"] for row in result["clinical_comparators"]}
    assert {"olaparib", "veliparib"} <= comparator_names
    olaparib = next(
        row for row in result["clinical_comparators"] if row["canonical"] == "olaparib"
    )
    assert olaparib["predictor_evidence"]["q2_model_reliability"] is not None
    assert olaparib["predictor_evidence"][
        "reference_cohort_sensitivity_percentile"
    ] is not None
    assert olaparib["evidence_concordance"] in {
        "concordant_high",
        "expression_only",
        "predictor_only",
        "low_or_uncertain",
    }
    assert result["predictor_summary"]["role"] == "parallel_clinical_context_not_nomination"
    assert any(
        row["combination"] == "cisplatin + doxorubicin"
        for row in result["predictor_combinations"]
    )
    assert "almanac_combinations" in result
    assert result.get("list1_drugs") is not None
    assert check_safety(json.dumps(result)) == []


def test_async_progress_and_completion(client, real_synthetic_patient):
    payload = {
        "patient_label": real_synthetic_patient["synthetic_id"],
        "expression": real_synthetic_patient["expression"],
        "metadata": real_synthetic_patient["metadata"],
        "administered_regimen": real_synthetic_patient["administered_regimen"],
        "top_up": 30,
        "top_down": 30,
    }
    ack = client.post("/analysis/async", json=payload)
    assert ack.status_code == 200, ack.text
    run_id = ack.json()["run_id"]
    deadline = time.time() + 60
    progress = None
    while time.time() < deadline:
        progress = client.get(f"/analysis/{run_id}/progress").json()
        if progress["status"] in {"completed", "failed"}:
            break
        time.sleep(0.4)
    assert progress is not None
    assert progress["status"] == "completed"
    assert any(s["stage_id"] == "calibrate_set" for s in progress["stages"])


def test_recalculate_creates_revision(client, real_synthetic_patient):
    submitted = _submit(client, real_synthetic_patient, top_up=30, top_down=30)
    run_id = submitted["run_id"]
    response = client.post(f"/analysis/{run_id}/recalculate", json={"top_up": 50, "top_down": 40})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["revision"] == 1
    assert result["signature_params"]["top_up"] == 50
    assert result["signature_params"]["top_down"] == 40


def test_persisted_chat_and_active_view(client, real_synthetic_patient):
    submitted = _submit(client, real_synthetic_patient, top_up=20, top_down=20)
    run_id = submitted["run_id"]
    chat = client.post(
        f"/analysis/{run_id}/chat",
        json={
            "message": "Summarize the overlap nominations",
            "history": [],
            "active_view": "patient_analysis",
        },
    )
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert body["answer"]
    assert check_safety(body["answer"]) == []
    history = client.get(f"/analysis/{run_id}/chat")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert any(m["role"] == "user" for m in messages)
    assert any(m["role"] == "assistant" for m in messages)


def test_run_level_trials_endpoint(client, real_synthetic_patient):
    submitted = _submit(client, real_synthetic_patient, top_up=20, top_down=20)
    response = client.get(f"/analysis/{submitted['run_id']}/trials")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == submitted["run_id"]
    assert "trials" in payload


def test_v2_exports(client, real_synthetic_patient):
    submitted = _submit(client, real_synthetic_patient, top_up=20, top_down=20)
    run_id = submitted["run_id"]
    json_resp = client.get(f"/analysis/{run_id}/export/json")
    assert json_resp.status_code == 200
    body = json.loads(json_resp.content)
    assert body["revision"] == 0
    assert "overlap_nominations" in (body.get("result") or {})
    csv_resp = client.get(f"/analysis/{run_id}/export/csv")
    assert csv_resp.status_code == 200
    assert b"weaker_percentile" in csv_resp.content or b"drug" in csv_resp.content
    pdf_resp = client.get(f"/analysis/{run_id}/export/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"