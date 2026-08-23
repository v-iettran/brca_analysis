from __future__ import annotations

import pandas as pd
import pytest

from pipeline_core import gctx_evidence


def _toy_table(ranks: dict[str, int], targets: dict[str, str] | None = None) -> pd.DataFrame:
    targets = targets or {}
    n = len(ranks)
    df = pd.DataFrame(
        {
            "drug": list(ranks.keys()),
            "drug_rank": list(ranks.values()),
            "reversal_score": [-1.0 * r for r in ranks.values()],
            "median_score": [None] * n,
            "n_signatures": [1] * n,
            "targets": [targets.get(d) for d in ranks.keys()],
        }
    )
    df["drug_lower"] = df["drug"].str.lower().str.strip()
    df["percentile"] = 1.0 - (df["drug_rank"] - 1) / max(n - 1, 1)
    return df.set_index("drug_lower")


@pytest.fixture
def toy_tables() -> dict[int, pd.DataFrame]:
    return {
        0: _toy_table({"olaparib": 1, "paclitaxel": 2, "cisplatin": 3}, {"olaparib": "PARP1;PARP2"}),
        1: _toy_table({"paclitaxel": 1, "cisplatin": 2, "olaparib": 4}),
    }


def test_drug_evidence_for_cluster_computes_percentile_from_rank(monkeypatch, toy_tables):
    monkeypatch.setattr(gctx_evidence, "load_all_cluster_drug_tables", lambda: toy_tables)

    evidence = gctx_evidence.drug_evidence_for_cluster(0, "olaparib")

    assert evidence is not None
    assert evidence["drug_rank"] == 1
    # Rank 1 of 3 drugs is always the top (strongest reversal) percentile.
    assert evidence["percentile"] == pytest.approx(1.0)
    assert evidence["targets"] == ["PARP1", "PARP2"]
    assert evidence["n_drugs_in_cluster"] == 3


def test_drug_evidence_for_cluster_unknown_drug_returns_none(monkeypatch, toy_tables):
    monkeypatch.setattr(gctx_evidence, "load_all_cluster_drug_tables", lambda: toy_tables)

    assert gctx_evidence.drug_evidence_for_cluster(0, "not-a-real-drug") is None
    assert gctx_evidence.drug_evidence_for_cluster(99, "olaparib") is None


def test_blended_drug_evidence_weights_by_cluster_probability(monkeypatch, toy_tables):
    monkeypatch.setattr(gctx_evidence, "load_all_cluster_drug_tables", lambda: toy_tables)

    # olaparib: percentile 1.0 in cluster 0, percentile 0.0 in cluster 1 (rank 4 of 4... wait 3 drugs).
    blended = gctx_evidence.blended_drug_evidence({0: 0.75, 1: 0.25}, "olaparib")

    cluster0_pct = gctx_evidence.drug_evidence_for_cluster(0, "olaparib")["percentile"]
    cluster1_pct = gctx_evidence.drug_evidence_for_cluster(1, "olaparib")["percentile"]
    expected = 0.75 * cluster0_pct + 0.25 * cluster1_pct

    assert blended["clusters_with_data"] == 2
    assert blended["blended_percentile"] == pytest.approx(expected)


def test_blended_drug_evidence_missing_from_all_clusters_returns_none(monkeypatch, toy_tables):
    monkeypatch.setattr(gctx_evidence, "load_all_cluster_drug_tables", lambda: toy_tables)

    blended = gctx_evidence.blended_drug_evidence({0: 0.5, 1: 0.5}, "unknown-drug")

    assert blended["clusters_with_data"] == 0
    assert blended["blended_percentile"] is None


def test_top_candidate_drugs_ranks_by_blended_percentile(monkeypatch, toy_tables):
    monkeypatch.setattr(gctx_evidence, "load_all_cluster_drug_tables", lambda: toy_tables)

    ranked = gctx_evidence.top_candidate_drugs({0: 0.6, 1: 0.4}, top_n=2)

    assert list(ranked.columns[:2]) == ["drug", "blended_percentile"]
    assert len(ranked) == 2
    assert ranked["blended_percentile"].is_monotonic_decreasing
