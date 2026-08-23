from pipeline_core.signatures import one_vs_rest_signature


def test_one_vs_rest_signature_recovers_known_direction(toy_expression, toy_labels):
    sig = one_vs_rest_signature(toy_expression, toy_labels, cluster_id=0)
    # Genes 0-9 were constructed to be up in cluster 0 -> positive coef, low p-value.
    up_genes = [f"GENE{i}" for i in range(10)]
    assert (sig.loc[up_genes, "coef"] > 0).all()
    assert (sig.loc[up_genes, "pval"] < 0.01).all()

    # Genes 10-19 are up in cluster 1 (down in cluster 0).
    down_genes = [f"GENE{i}" for i in range(10, 20)]
    assert (sig.loc[down_genes, "coef"] < 0).all()

    # Untouched genes should show no strong signal.
    neutral_genes = [f"GENE{i}" for i in range(20, 40)]
    assert (sig.loc[neutral_genes, "pval"] > 0.05).mean() > 0.7
