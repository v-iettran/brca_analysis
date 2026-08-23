from __future__ import annotations

import pandas as pd
import pytest

from pipeline_core import q2_evidence


@pytest.fixture
def toy_coefficients() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "drug": ["drugA", "drugA", "drugA", "drugA", "drugB"],
            "feature": ["GENE1", "GENE2", "GENE3", "GENE4", "GENE1"],
            "coefficient": [1.0, -1.0, 2.0, 0.0, 0.5],
        }
    )


def test_weighted_signature_score_matches_manual_calculation(monkeypatch, toy_coefficients):
    monkeypatch.setattr(q2_evidence, "load_q2_coefficients", lambda: toy_coefficients)
    z_scores = pd.Series({"GENE1": 1.0, "GENE2": 2.0, "GENE3": -0.5, "GENE4": 5.0, "GENE5": 9.0})

    score, genes_used = q2_evidence.weighted_signature_score(z_scores, "drugA")

    # GENE4's coefficient is zero and is dropped, leaving 3 genes -- exactly the
    # MINIMUM_GENES guard, so the score should still be returned.
    expected = (1.0 * 1.0 + (-1.0) * 2.0 + 2.0 * (-0.5)) / (1.0 + 1.0 + 2.0)
    assert genes_used == 3
    assert score == pytest.approx(expected)


def test_weighted_signature_score_returns_none_below_minimum_genes(monkeypatch, toy_coefficients):
    monkeypatch.setattr(q2_evidence, "load_q2_coefficients", lambda: toy_coefficients)
    # drugB only has one non-zero, covered gene -- below MINIMUM_GENES (3).
    z_scores = pd.Series({"GENE1": 1.0})

    score, genes_used = q2_evidence.weighted_signature_score(z_scores, "drugB")

    assert score is None
    assert genes_used == 1


def test_weighted_signature_score_ignores_uncovered_genes(monkeypatch, toy_coefficients):
    monkeypatch.setattr(q2_evidence, "load_q2_coefficients", lambda: toy_coefficients)
    # Patient only has two of drugA's four coefficient genes covered.
    z_scores = pd.Series({"GENE1": 1.0, "GENE3": -0.5})

    score, genes_used = q2_evidence.weighted_signature_score(z_scores, "drugA")

    assert score is None
    assert genes_used == 2


def test_available_drugs_lists_unique_sorted_drugs(monkeypatch, toy_coefficients):
    monkeypatch.setattr(q2_evidence, "load_q2_coefficients", lambda: toy_coefficients)

    assert q2_evidence.available_drugs() == ["drugA", "drugB"]
