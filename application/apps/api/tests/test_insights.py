from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pipeline_core.safety import check_safety

from app.services import literature_service

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _submit(client, patient: dict) -> dict:
    response = client.post(
        "/analysis",
        json={
            "patient_label": patient["synthetic_id"],
            "expression": patient["expression"],
            "metadata": patient["metadata"],
            "administered_regimen": patient["administered_regimen"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_cluster_detail_exposes_positive_and_negative_signature_genes(
    client, real_synthetic_patient
):
    run = _submit(client, real_synthetic_patient)
    cluster_id = run["cluster_prediction"]["top_cluster"]

    response = client.get(f"/analysis/{run['run_id']}/clusters/{cluster_id}?top_n=8")

    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["patient_probability"] > 0
    assert len(detail["positive_genes"]) == 8
    assert len(detail["negative_genes"]) == 8
    assert all(gene["coefficient"] > 0 for gene in detail["positive_genes"])
    assert all(gene["coefficient"] < 0 for gene in detail["negative_genes"])
    assert "PAM50-adjusted" in detail["coefficient_interpretation"]


def test_gene_literature_uses_paperclip_fixture(client, real_synthetic_patient, monkeypatch):
    run = _submit(client, real_synthetic_patient)
    cluster_id = run["cluster_prediction"]["top_cluster"]
    detail = client.get(f"/analysis/{run['run_id']}/clusters/{cluster_id}?top_n=5").json()
    gene = detail["positive_genes"][0]["gene"]
    raw = json.loads((FIXTURES_DIR / "paperclip_search.json").read_text())

    class FakePaperclipClient:
        def search(self, query, **kwargs):
            return SimpleNamespace(output=f"fixture for {query}", raw=raw, result_id="gene")

    monkeypatch.setattr(literature_service, "get_paperclip_client", lambda: FakePaperclipClient())
    response = client.get(
        f"/analysis/{run['run_id']}/clusters/{cluster_id}/genes/{gene}/literature"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["gene"] == gene
    assert body["cluster_id"] == cluster_id
    assert body["deduplicated_count"] == 2
    assert "does not validate" in body["interpretation_note"]
    assert [citation["evidence_rank"] for citation in body["citations"]] == [1, 2]
    assert all(citation["combined_score"] is not None for citation in body["citations"])


def test_copilot_chat_uses_run_context_and_safe_language(client, real_synthetic_patient):
    run = _submit(client, real_synthetic_patient)

    response = client.post(
        f"/analysis/{run['run_id']}/chat",
        json={"message": "Explain the Q5 pCR result in plain language."},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "Q5" in body["answer"]
    assert any(source["section"] == "q5" for source in body["sources"])
    assert check_safety(json.dumps(body)) == []

    predictor_response = client.post(
        f"/analysis/{run['run_id']}/chat",
        json={"message": "Explain the olaparib Predictor and Q4 support."},
    )
    assert predictor_response.status_code == 200, predictor_response.text
    predictor_body = predictor_response.json()
    assert "reference-cohort Q2 sensitivity" in predictor_body["answer"]
    assert "does not alter List 1/List 2" in predictor_body["answer"]
    assert check_safety(json.dumps(predictor_body)) == []
