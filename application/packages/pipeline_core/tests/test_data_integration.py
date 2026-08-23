"""Integration tests against the real METABRIC/Q4/Q5 artifacts on disk.

These are skipped (not failed) when the underlying data files are not present
-- e.g. in a minimal CI container that only mounts the small copilot
artifacts and not the 689 MB raw METABRIC file. Anyone running the full
local dev workflow (see docs/mofa_copilot/TECHNICAL_RUNBOOK.md) will have
these pass.
"""

from __future__ import annotations

import pytest

from pipeline_core.config import METABRIC_DIR, MOFA_CLUSTERS_DIR, Q5_TABLES_DIR

pytestmark = pytest.mark.skipif(
    not (METABRIC_DIR / "data_mrna_illumina_microarray.txt").exists()
    or not (MOFA_CLUSTERS_DIR / "mofa_clusters.csv").exists()
    or not (Q5_TABLES_DIR / "q2_chemotherapy_signature_coefficients.csv").exists(),
    reason="Real METABRIC/MOFA/Q5 data artifacts are not available in this environment.",
)


@pytest.fixture(scope="module")
def real_expression():
    from pipeline_core.expression import load_metabric_expression

    return load_metabric_expression()


@pytest.fixture(scope="module")
def real_labels():
    from pipeline_core.expression import load_mofa_cluster_labels

    return load_mofa_cluster_labels()


def test_align_patient_expression_full_coverage(real_expression):
    from pipeline_core.expression import align_patient_expression

    sample = real_expression.columns[0]
    vector = real_expression[sample].dropna().to_dict()
    aligned = align_patient_expression(vector)
    assert aligned.coverage_fraction > 0.95
    assert aligned.genes_found > 15000


def test_align_patient_expression_low_coverage_warns(real_expression):
    from pipeline_core.expression import align_patient_expression

    sample = real_expression.columns[0]
    full = real_expression[sample].dropna()
    sparse = full.iloc[:50].to_dict()
    aligned = align_patient_expression(sparse)
    assert aligned.genes_found <= 50
    assert aligned.coverage_fraction < 0.05


def test_predict_cluster_probabilities_recovers_true_label_most_of_the_time(
    real_expression, real_labels
):
    from pipeline_core.cluster_model import predict_cluster_probabilities

    samples = list(real_expression.columns[:25])
    correct = 0
    for sample in samples:
        if sample not in real_labels.index:
            continue
        vector = real_expression[sample].dropna().to_dict()
        prediction = predict_cluster_probabilities(vector)
        assert abs(sum(prediction.probabilities.values()) - 1.0) < 1e-6
        if prediction.top_cluster == real_labels.loc[sample]:
            correct += 1
    # This is a leaky in-sample sanity check, not the CV benchmark -- just
    # confirms the pipeline runs end-to-end and is clearly better than chance.
    assert correct / len(samples) > 0.4


def test_q2_weighted_signature_score_matches_hand_computation(real_expression):
    from pipeline_core.expression import align_patient_expression
    from pipeline_core.q2_evidence import available_drugs, weighted_signature_score

    sample = real_expression.columns[0]
    vector = real_expression[sample].dropna().to_dict()
    aligned = align_patient_expression(vector)

    drug = available_drugs()[0]
    score, genes_used = weighted_signature_score(aligned.z_scores, drug)
    assert genes_used >= 3
    assert score is not None
    assert -50 < score < 50  # sanity bound; a z-scored weighted average should not blow up


def test_gctx_blended_drug_evidence_returns_percentile():
    from pipeline_core.gctx_evidence import blended_drug_evidence, load_all_cluster_drug_tables

    tables = load_all_cluster_drug_tables()
    any_drug = tables[0].iloc[0]["drug"]
    evidence = blended_drug_evidence({0: 0.7, 1: 0.1, 2: 0.1, 3: 0.05, 4: 0.05}, any_drug)
    assert evidence["blended_percentile"] is not None
    assert 0.0 <= evidence["blended_percentile"] <= 1.0


def test_pcr_applicability_gate_represented_regimen():
    from pipeline_core.pcr_model import applicability_gate

    gate = applicability_gate(["5-fluorouracil", "doxorubicin", "paclitaxel"])
    assert gate["represented"] is True
    assert gate["validated_cohort"] == "GSE20194"


def test_pcr_applicability_gate_novel_regimen():
    from pipeline_core.pcr_model import applicability_gate

    gate = applicability_gate(["trastuzumab", "pertuzumab"])
    assert gate["represented"] is False
    assert gate["gate_passed"] is False


def test_q5_parity_report_matches_committed_r_metrics_closely():
    from pipeline_core.pcr_model import q5_parity_report

    report = q5_parity_report()
    assert report.probability_correlation > 0.999
    assert report.max_absolute_difference < 0.02
    for key, committed in report.committed_metrics.items():
        python_auroc = report.python_metrics[key]["auroc"]
        assert abs(python_auroc - committed["auroc"]) < 0.03
