import pandas as pd
import pytest

from pipeline_core.predictor_evidence import (
    _empirical_percentile,
    attach_predictor_context,
    load_predictor_coefficients,
    load_predictor_support_tables,
    predictor_combinations,
)


def _predictor_row(drug: str, priority: float, q4: float, percentile: float = 0.8):
    return {
        "drug": drug,
        "integrated_single_drug_priority": priority,
        "q4_drug_support": q4,
        "within_patient_predictor_percentile": percentile,
    }


def test_predictor_combination_matches_r_weighting(monkeypatch):
    pairs = pd.DataFrame(
        [
            {
                "drug_a": "cisplatin",
                "drug_b": "doxorubicin",
                "combination": "cisplatin + doxorubicin",
                "aligned_pair_support": 0.8,
                "aligned_cell_lines": 5,
                "cell_line_alignment_confidence": "high_4_or_more_aligned_lines",
            }
        ]
    )
    monkeypatch.setattr(
        "pipeline_core.predictor_evidence.load_eligible_almanac_pairs", lambda: pairs
    )

    rows = predictor_combinations(
        [
            _predictor_row("cisplatin", 0.81, 0.4),
            _predictor_row("doxorubicin", 0.49, 0.2),
        ]
    )

    assert rows[0]["component_drug_priority"] == pytest.approx(0.63)
    assert rows[0]["pair_q4_support"] == pytest.approx(0.30)
    assert rows[0]["integrated_combination_priority"] == pytest.approx(
        0.55 * 0.63 + 0.35 * 0.8 + 0.10 * 0.30
    )


def test_concordance_keeps_predictor_separate_from_expression_rank():
    comparator = {
        "drug": "olaparib",
        "dual_support_percentile": 0.2,
    }
    rows = attach_predictor_context(
        [comparator], [_predictor_row("olaparib", 0.8, 0.5, percentile=0.9)]
    )

    assert rows[0]["evidence_concordance"] == "predictor_only"
    assert rows[0]["dual_support_percentile"] == 0.2
    assert rows[0]["predictor_evidence"]["integrated_single_drug_priority"] == 0.8


def test_python_inputs_match_committed_r_predictor_artifacts():
    coefficients = load_predictor_coefficients()
    support = load_predictor_support_tables()

    olaparib = coefficients[
        (coefficients["drug"] == "olaparib") & (coefficients["coefficient"] != 0)
    ]
    assert len(olaparib) == 12
    assert support.loc["olaparib", "q2_model_support"] == pytest.approx(
        0.238182960075172
    )
    assert support.loc["olaparib", "q4_drug_support"] == pytest.approx(
        0.13888671720831
    )


def test_empirical_percentile_matches_r_midrank_definition():
    reference = pd.Series([0.1, 0.2, 0.2, 0.9])
    assert _empirical_percentile(0.2, reference) == pytest.approx(0.5)
