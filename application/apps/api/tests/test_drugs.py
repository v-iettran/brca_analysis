"""Literature/trials endpoints, exercised entirely against local fixtures --
no network access to Paperclip or ClinicalTrials.gov is required or made."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import models_orm
from app.db import SessionLocal
from app.services import literature_service, trials_service

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_external_query_cache():
    """Each test exercises the SQLite cache explicitly -- start from empty so
    tests don't leak cached responses into each other."""
    db = SessionLocal()
    db.query(models_orm.ExternalQueryCache).delete()
    db.commit()
    db.close()
    yield


def _submit_and_get_drug(client, patient: dict) -> tuple[str, str]:
    payload = {
        "patient_label": patient["synthetic_id"],
        "expression": patient["expression"],
        "metadata": patient["metadata"],
        "administered_regimen": patient["administered_regimen"],
    }
    result = client.post("/analysis", json=payload).json()
    drug = result["top_candidate_drugs"][0]["drug"]
    return result["run_id"], drug


class _FakePaperclipClient:
    def __init__(self, fixture_path: Path):
        self._raw = json.loads(fixture_path.read_text())

    def search(self, query, **kwargs):
        return SimpleNamespace(output=f"fixture results for {query}", raw=self._raw, result_id="s_fixture")


def test_drug_literature_uses_fixture_and_dedupes(client, real_synthetic_patient, monkeypatch):
    run_id, drug = _submit_and_get_drug(client, real_synthetic_patient)

    fake_client = _FakePaperclipClient(FIXTURES_DIR / "paperclip_search.json")
    monkeypatch.setattr(literature_service, "get_paperclip_client", lambda: fake_client)

    response = client.get(f"/analysis/{run_id}/drugs/{drug}/literature")
    assert response.status_code == 200
    body = response.json()
    assert body["deduplicated_count"] == 2  # 2 unique DOIs, seen across 4 query families
    assert body["cache_hit"] is False
    stances = {c["stance"] for c in body["citations"]}
    assert stances.issubset({"supporting", "conflicting", "neutral", "unclear"})
    assert [c["evidence_rank"] for c in body["citations"]] == [1, 2]
    assert all(c["credibility_score"] is not None for c in body["citations"])
    assert all(c["relevance_score"] is not None for c in body["citations"])

    # Second call should hit the SQLite cache.
    response2 = client.get(f"/analysis/{run_id}/drugs/{drug}/literature")
    assert response2.json()["cache_hit"] is True


def test_drug_literature_unavailable_without_client(client, real_synthetic_patient, monkeypatch):
    run_id, drug = _submit_and_get_drug(client, real_synthetic_patient)
    monkeypatch.setattr(literature_service, "get_paperclip_client", lambda: None)

    response = client.get(f"/analysis/{run_id}/drugs/{drug}/literature")
    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert "unavailable_reason" in body


def test_drug_trials_uses_fixture_and_ranks_ireland_first(client, real_synthetic_patient, monkeypatch):
    run_id, drug = _submit_and_get_drug(client, real_synthetic_patient)
    fixture = json.loads((FIXTURES_DIR / "clinicaltrials_search.json").read_text())

    class _FakeHttpxClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, timeout=None):
            return httpx.Response(200, json=fixture, request=httpx.Request("GET", url))

    monkeypatch.setattr(trials_service.httpx, "Client", lambda: _FakeHttpxClient())

    response = client.get(f"/analysis/{run_id}/drugs/{drug}/trials")
    assert response.status_code == 200
    body = response.json()
    assert len(body["trials"]) == 1
    sites = body["trials"][0]["sites"]
    assert sites[0]["country"] == "Ireland"
    assert sites[0]["tier"] == 0


def test_drug_literature_unknown_run_404(client):
    response = client.get("/analysis/does-not-exist/drugs/docetaxel/literature")
    assert response.status_code == 404
