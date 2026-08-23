"""Unit tests for V2 overlap nomination core."""

from __future__ import annotations

import pandas as pd

from pipeline_core.almanac_evidence import combinations_for_overlap
from pipeline_core.nominations import adjudicate_hit, nominate_overlap
from pipeline_core.residual_signatures import clamp_signature_size


def test_clamp_signature_size_bounds():
    assert clamp_signature_size(None, 150) == 150
    assert clamp_signature_size(1, 150) == 10
    assert clamp_signature_size(9999, 150) == 300


def test_residual_direction_selection():
    residual = pd.Series({f"G{i}": float(i - 50) for i in range(100)})
    top_up, top_down = 10, 5
    up_rows = residual.sort_values(ascending=False).head(top_up)
    up_rows = up_rows[up_rows > 0]
    down_rows = residual.sort_values(ascending=True).head(top_down)
    down_rows = down_rows[down_rows < 0]
    assert len(up_rows) == 10
    assert len(down_rows) == 5
    assert all(v > 0 for v in up_rows)
    assert all(v < 0 for v in down_rows)


def test_nominate_overlap_requires_both_lists_and_ranks_by_weaker():
    list1 = pd.DataFrame(
        [
            {"drug": "alpha", "canonical": "alpha", "percentile": 0.99, "rank": 1, "reversal_score": 1.0, "targets": ["A"]},
            {"drug": "beta", "canonical": "beta", "percentile": 0.80, "rank": 2, "reversal_score": 0.8, "targets": []},
            {"drug": "solo1", "canonical": "solo1", "percentile": 0.95, "rank": 3, "reversal_score": 0.9, "targets": []},
        ]
    )
    list2 = pd.DataFrame(
        [
            {"drug": "alpha", "canonical": "alpha", "percentile": 0.70, "rank": 2, "reversal_score": 0.7, "targets": ["A"]},
            {"drug": "beta", "canonical": "beta", "percentile": 0.90, "rank": 1, "reversal_score": 0.9, "targets": []},
            {"drug": "solo2", "canonical": "solo2", "percentile": 0.95, "rank": 3, "reversal_score": 0.9, "targets": []},
        ]
    )
    result = nominate_overlap(list1, list2, top_n=10)
    drugs = [row["drug"] for row in result["overlap"]]
    assert "solo1" not in drugs and "solo2" not in drugs
    assert drugs[0] == "beta"  # weaker=0.80 beats alpha weaker=0.70
    assert result["n_overlap"] == 2


def test_adjudicate_flags_missing_targets_and_stress():
    flags = adjudicate_hit(
        {"canonical": "tanespimycin", "targets": [], "n_cell_lines": 1, "consistency": 0.2},
        0.4,
        0.9,
    )
    assert flags.missing_target_pathway_support
    assert flags.generic_stress_pattern
    assert flags.likely_artifact


def test_q2_absence_does_not_remove_nomination():
    list1 = pd.DataFrame(
        [{"drug": "novel-x", "canonical": "novel-x", "percentile": 0.95, "rank": 1, "reversal_score": 1.0, "targets": ["X"]}]
    )
    list2 = pd.DataFrame(
        [{"drug": "novel-x", "canonical": "novel-x", "percentile": 0.94, "rank": 1, "reversal_score": 0.9, "targets": ["X"]}]
    )
    result = nominate_overlap(list1, list2)
    assert len(result["overlap"]) == 1
    assert "q2" not in result["overlap"][0]


def test_almanac_pair_gating_requires_both_overlap_drugs(monkeypatch):
    pairs = pd.DataFrame(
        [
            {
                "drug_a": "alpha",
                "drug_b": "beta",
                "combination": "alpha + beta",
                "aligned_cell_lines": 2,
                "aligned_pair_support": 0.8,
                "aligned_median_almanac_combo_score": 1.0,
                "cell_line_alignment_confidence": "high",
            },
            {
                "drug_a": "alpha",
                "drug_b": "gamma",
                "combination": "alpha + gamma",
                "aligned_cell_lines": 3,
                "aligned_pair_support": 0.9,
                "aligned_median_almanac_combo_score": 1.0,
                "cell_line_alignment_confidence": "high",
            },
        ]
    )
    monkeypatch.setattr(
        "pipeline_core.almanac_evidence.load_eligible_almanac_pairs",
        lambda: pairs.assign(
            drug_a_canonical=pairs["drug_a"],
            drug_b_canonical=pairs["drug_b"],
        ),
    )
    combos = combinations_for_overlap(["alpha", "beta"])
    assert len(combos) == 1
    assert combos[0]["combination"] == "alpha + beta"
