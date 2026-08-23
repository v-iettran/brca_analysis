from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_core import pcr_model
from pipeline_core.config import Q5_TABLES_DIR

_METRICS_PATH = Q5_TABLES_DIR / "patient_external_validation_metrics.csv"
requires_q5_data = pytest.mark.skipif(
    not Path(_METRICS_PATH).exists(), reason="Q5 validation metrics not available in this environment"
)


class TestMatchRepresentedRegimen:
    def test_matches_gse20194_style_regimen_regardless_of_order(self):
        spec = pcr_model._match_represented_regimen(["Paclitaxel", "doxorubicin", "5-Fluorouracil"])

        assert spec is not None
        assert spec["cohort"] == "GSE20194"

    def test_matches_either_taxane_option(self):
        docetaxel_spec = pcr_model._match_represented_regimen(
            ["5-fluorouracil", "doxorubicin", "docetaxel"]
        )
        assert docetaxel_spec is not None
        assert "docetaxel" in docetaxel_spec["taxane_options"]

    def test_missing_base_drug_does_not_match(self):
        spec = pcr_model._match_represented_regimen(["paclitaxel", "doxorubicin"])

        assert spec is None

    def test_missing_taxane_does_not_match(self):
        spec = pcr_model._match_represented_regimen(["5-fluorouracil", "doxorubicin"])

        assert spec is None

    def test_unrelated_regimen_does_not_match(self):
        spec = pcr_model._match_represented_regimen(["olaparib", "trastuzumab"])

        assert spec is None


class TestBinaryMetrics:
    def test_perfect_separation_gives_auroc_one(self):
        import numpy as np

        metrics = pcr_model._binary_metrics(
            np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])
        )

        assert metrics["auroc"] == pytest.approx(1.0)
        assert metrics["n"] == 4
        assert metrics["positives"] == 2

    def test_single_class_returns_none_auroc(self):
        import numpy as np

        metrics = pcr_model._binary_metrics(np.array([1, 1, 1]), np.array([0.7, 0.8, 0.9]))

        assert metrics["auroc"] is None


@requires_q5_data
class TestApplicabilityGate:
    def test_represented_regimen_reports_cohort_and_gate(self):
        gate = pcr_model.applicability_gate(["5-fluorouracil", "doxorubicin", "paclitaxel"])

        assert gate["represented"] is True
        assert gate["validated_cohort"] in {"GSE20194", "GSE25065"}
        assert gate["gate_threshold"] == pcr_model.PCR_APPLICABILITY_GATE_AUROC_MIN

    def test_unrepresented_regimen_is_never_gated_open(self):
        gate = pcr_model.applicability_gate(["some-novel-mofa-drug"])

        assert gate["represented"] is False
        assert gate["gate_passed"] is False
        assert "discovery hypothesis" in gate["reason"]
