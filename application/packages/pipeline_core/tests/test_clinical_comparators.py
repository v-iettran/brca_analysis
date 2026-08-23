import pandas as pd

from pipeline_core.clinical_comparators import expression_ranked_comparators


def test_clinical_comparators_preserve_actual_expression_ranks():
    list1 = pd.DataFrame(
        [
            {"drug": "olaparib", "canonical": "olaparib", "rank": 187, "percentile": 0.72, "targets": ["PARP1"]},
            {"drug": "curcumin", "canonical": "curcumin", "rank": 1, "percentile": 1.0, "targets": []},
        ]
    )
    list2 = pd.DataFrame(
        [
            {"drug": "olaparib", "canonical": "olaparib", "rank": 436, "percentile": 0.31, "targets": ["PARP2"]},
            {"drug": "curcumin", "canonical": "curcumin", "rank": 2, "percentile": 0.99, "targets": []},
        ]
    )

    rows = expression_ranked_comparators(list1, list2)

    assert [row["canonical"] for row in rows] == ["olaparib"]
    assert rows[0]["list1_rank"] == 187
    assert rows[0]["list2_rank"] == 436
    assert rows[0]["dual_support_percentile"] == 0.31
    assert rows[0]["category"] == "PARP inhibitor"


def test_cluster_reference_surfaces_parpi_without_inventing_residual_rank():
    reference = pd.DataFrame(
        [
            {
                "drug": "veliparib",
                "drug_rank": 911,
                "percentile": 0.12,
                "targets": "PARP1;PARP2",
            }
        ]
    )

    rows = expression_ranked_comparators(pd.DataFrame(), pd.DataFrame(), reference)

    assert rows[0]["canonical"] == "veliparib"
    assert rows[0]["list1_rank"] == 911
    assert rows[0]["list2_rank"] is None
    assert rows[0]["dual_support_percentile"] is None
    assert rows[0]["list1_source"] == "mofa_cluster_reference_gctx"
