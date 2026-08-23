from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# Must happen before `app.*` modules are imported anywhere in the test
# session, since pipeline_core.config/app.config read these once at import
# time. Using a throwaway SQLite file keeps tests from touching the real
# copilot.db.
_TMP_DB = Path(tempfile.mkdtemp()) / "test_copilot.db"
os.environ["COPILOT_DB_PATH"] = str(_TMP_DB)
os.environ.setdefault("OLLAMA_ENABLED", "false")
# Prevent analysis submission fixtures from making live Paperclip calls.
# Endpoint tests explicitly monkeypatch a fake Paperclip client.
os.environ.setdefault("PAPERCLIP_API_KEY", "")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from pipeline_core.config import SYNTHETIC_PATIENTS_DIR  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    init_db()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def real_synthetic_patient() -> dict:
    """Load a real, already-generated synthetic patient (small, fast fixture
    reused across tests instead of regenerating from raw METABRIC)."""
    candidates = sorted(SYNTHETIC_PATIENTS_DIR.glob("SYN-HIG-*.json"))
    if not candidates:
        pytest.skip(
            "No synthetic patients found; run `python jobs/generate_synthetic_patients.py` first."
        )
    return json.loads(candidates[0].read_text())


@pytest.fixture(scope="session")
def low_quality_synthetic_patient() -> dict:
    candidates = sorted(SYNTHETIC_PATIENTS_DIR.glob("SYN-LOW-*.json"))
    if not candidates:
        pytest.skip("No low-quality synthetic patient found.")
    return json.loads(candidates[0].read_text())
