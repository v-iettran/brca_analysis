import numpy as np

from pipeline_core.cluster_model import (
    _cosine_similarity_scores,
    _softmax,
    cross_validate_elastic_net,
    cross_validate_signature_similarity,
)
from pipeline_core.signatures import one_vs_rest_signature


def test_softmax_sums_to_one_and_favors_larger_score():
    probs = _softmax({0: 2.0, 1: 0.0, 2: -2.0}, temperature=0.5)
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert probs[0] > probs[1] > probs[2]


def test_cosine_similarity_scores_prefers_matching_signature(toy_expression, toy_labels):
    signatures = {
        0: one_vs_rest_signature(toy_expression, toy_labels, 0),
        1: one_vs_rest_signature(toy_expression, toy_labels, 1),
    }
    ref_mean, ref_sd = toy_expression.mean(axis=1), toy_expression.std(axis=1)
    sample_a = toy_expression["S_A0"]
    z_a = (sample_a - ref_mean) / ref_sd

    scores = _cosine_similarity_scores(z_a, signatures, top_n=20)
    assert scores[0] > scores[1]


def test_cross_validate_signature_similarity_beats_chance(toy_expression, toy_labels):
    metrics = cross_validate_signature_similarity(toy_expression, toy_labels, n_folds=3, top_n=20)
    assert metrics.n_samples == 30
    assert metrics.accuracy > 0.6  # chance is 0.5 for 2 balanced classes


def test_cross_validate_elastic_net_beats_chance(toy_expression, toy_labels):
    metrics = cross_validate_elastic_net(toy_expression, toy_labels, n_folds=3, top_n_genes=20)
    assert metrics.accuracy > 0.6
    assert metrics.n_genes_used == 20
