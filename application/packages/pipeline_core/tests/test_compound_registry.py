"""Compound registry lookup and seed coverage."""

from __future__ import annotations

import pandas as pd

from pipeline_core.compound_registry import (
    HUMAN_DEVELOPMENT_STATUSES,
    _row_from_mapping,
    is_anonymous_perturbagen,
    lookup_compound,
)
from pipeline_core import compound_registry as registry_mod
from pipeline_core.compound_registry_seed import seed_records
from pipeline_core.drug_names import normalize_drug_name
from pipeline_core.nominations import BREAST_CONTEXT_DRUGS


def test_seed_covers_breast_context_and_status_vocabulary():
    records = {row["canonical"]: row for row in seed_records()}
    for name in BREAST_CONTEXT_DRUGS:
        assert normalize_drug_name(name) in records
    statuses = {row["human_development_status"] for row in records.values()}
    assert statuses <= set(HUMAN_DEVELOPMENT_STATUSES)
    assert records["paclitaxel"]["display_action"] == "default_visible"
    assert records["emetine"]["display_action"] == "technical_excluded"


def test_anonymous_perturbagen_detection():
    assert is_anonymous_perturbagen("BRD-K12345678")
    assert is_anonymous_perturbagen("SA-123456")
    assert not is_anonymous_perturbagen("paclitaxel")


def test_lookup_uses_canonical_seed_rows(monkeypatch):
    frame = pd.DataFrame([_row_from_mapping(row) for row in seed_records()])
    monkeypatch.setattr(registry_mod, "load_registry", lambda: frame)
    hit = lookup_compound(name="paclitaxel")
    assert hit is not None
    assert hit["human_development_status"] in HUMAN_DEVELOPMENT_STATUSES
    assert hit["match_key"] == "canonical"
    assert lookup_compound(name="not-a-real-drug-xyz") is None
