"""v3 payload contracts, clustering invariants, and failure branches."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from cluster_selection import (
    STABILITY_THRESHOLD,
    assert_no_survival,
    config_id,
    fit_gmm,
    freeze_preregistered_k,
    model_selection_table,
    precompute_configurations,
    select_k_star,
)
from cluster_stats import annotate_clusters, comparison_matrix, mannwhitney_one_vs_rest
from gctx_retrieval import SOURCE_SMOKE, known_drug_positive_control, rank_reversal
from methylation_tf_reliability import completeness_flag, methylation_silencing_reliability
from nearest_lines import hill_viability, nearest_lines, sample_dose_curve, subtype_concordance
from safety import assert_safe
from survival_export import kaplan_meier, multivariate_logrank, sensitivity_logrank
from tcga_normals import patient_from_barcode, sample_type_from_barcode, split_tumour_normal
from v3_payload import (
    SCHEMA_VERSION,
    glossary_allows_nll,
    validate_cohort,
    validate_patient,
)
from v3_smoke import assemble_v3, persist_smoke


def test_k_selection_rejects_survival_columns():
    df = pd.DataFrame({"z0": [1.0], "OS_MONTHS": [12.0]})
    with pytest.raises(ValueError, match="Survival"):
        assert_no_survival(df)


def test_select_k_star_uses_stability_within_bic_window():
    bic = {2: 100.0, 3: 105.0, 4: 140.0}
    sil = {2: 0.2, 3: 0.4, 4: 0.9}
    stability = {2: 0.55, 3: 0.81, 4: 0.99}
    assert select_k_star(bic, sil, stability) == 3


def test_preregistered_config_id_and_exploratory_flag():
    assert config_id("gmm", "full", 4) == "gmm:full:k=4"
    assert config_id("kmeans", None, 3) == "kmeans:na:k=3"


def test_bootstrap_selection_reproducible(tmp_path):
    rng = np.random.default_rng(1)
    Z = np.vstack([
        rng.normal(loc=[2, 0], scale=0.2, size=(40, 2)),
        rng.normal(loc=[-2, 0], scale=0.2, size=(40, 2)),
        rng.normal(loc=[0, 2], scale=0.2, size=(40, 2)),
    ])
    a = model_selection_table(Z, n_boot=6, n_init=2, random_state=0)
    b = model_selection_table(Z, n_boot=6, n_init=2, random_state=0)
    assert a == b
    k = select_k_star({r["k"]: r["bic"] for r in a}, {r["k"]: r["silhouette"] for r in a}, {r["k"]: r["stability"] for r in a})
    rec = freeze_preregistered_k(k, next(r for r in a if r["k"] == k), True)
    (tmp_path / "preregistered_k.json").write_text(json.dumps(rec))
    assert rec["selection_rule"] == "stability_within_10_bic"
    assert rec["method"] == "gmm"


def test_exploratory_km_omits_p_and_preregistered_keeps_it():
    cohort, patients = assemble_v3(n=90, n_boot=8)
    assert validate_cohort(cohort) == []
    preg = cohort["preregistered"]
    preg_id = f"gmm:full:k={preg['k']}"
    assert cohort["configurations"][preg_id]["exploratory"] is False
    assert cohort["configurations"][preg_id]["km"]["os"]["p_value"] is not None
    other = next(cid for cid, cfg in cohort["configurations"].items() if cfg["exploratory"])
    assert cohort["configurations"][other]["km"]["os"]["p_value"] is None
    assert all(row["exploratory"] is True for row in cohort["survival_sensitivity"])


def test_a2_failure_is_descriptive_not_an_implementation_error():
    cohort, _ = assemble_v3(n=90, n_boot=8, a2_must_pass=False)
    if not cohort["gates"]["a2"]["passed"]:
        assert cohort["gates"]["a2"]["framing"] == "descriptive"


def test_logrank_separates_shifted_groups():
    t = np.concatenate([np.linspace(20, 80, 40), np.linspace(5, 25, 40)])
    e = np.ones(80)
    g = np.array([0] * 40 + [1] * 40)
    res = multivariate_logrank(t, g, e)
    assert res["p_value"] < 0.05
    km = kaplan_meier(t[:40], e[:40])
    assert km["median"] is not None


def test_comparison_matrix_shape_and_pathway_gate():
    rng = np.random.default_rng(0)
    labels = np.repeat([0, 1, 2], 30)
    values = pd.DataFrame(rng.normal(size=(90, 6)), columns=list("ABCDEF"))
    for lab, col in enumerate("ABC"):
        values.loc[labels == lab, col] += 3.0
    prof = mannwhitney_one_vs_rest(values, labels, "pathway")
    matrix = comparison_matrix(prof, top_n=6)
    assert len(matrix["clusters"]) == 3
    assert len(matrix["features"]) == 6
    assert np.array(matrix["effects"]).shape == (6, 3)


def test_methylation_reliability_not_completeness():
    act = pd.DataFrame({"ESR1": [1.0, np.nan, 0.5]})
    comp = completeness_flag(act)
    meth = pd.DataFrame({"ESR1": [0.9, 0.85, 0.8]})
    rel = methylation_silencing_reliability({"ESR1": ["ESR1"]}, meth)
    missing = methylation_silencing_reliability({"ESR1": ["ESR1"]}, None)
    assert rel.loc[0, "source"] == "methylation"
    assert missing.loc[0, "source"] == "unavailable"
    assert float(comp["ESR1"]) != rel.loc[0, "silenced_fraction"]


def test_tcga_barcode_normal_and_patient():
    assert sample_type_from_barcode("TCGA-A8-A081-11A-01R") == "11"
    assert sample_type_from_barcode("TCGA-A8-A081-01A-01R") == "01"
    assert patient_from_barcode("TCGA-A8-A081-01A") == "TCGA-A8-A081"
    tumours, normals = split_tumour_normal(["TCGA-A8-A081-01A", "TCGA-A8-A081-11A"])
    assert len(tumours) == 1 and len(normals) == 1


def test_positive_control_and_proxy_source():
    sig = pd.Series({"ESR1": 2.0, "PGR": 1.5, "FOXA1": 1.2, "MKI67": 0.4, "ERBB2": -0.2, "CCNB1": 0.1})
    pert = pd.DataFrame(
        {
            "ESR1": [-2, 0, 1],
            "PGR": [-1.5, 0, 1],
            "FOXA1": [-1, 0, 1],
            "MKI67": [0, 0, 0],
            "ERBB2": [0, 0, 0],
            "CCNB1": [0, 0, 0],
        },
        index=["tamoxifen", "compound_x", "compound_y"],
    )
    hits = rank_reversal(sig, pert, source=SOURCE_SMOKE, top_n=3)
    assert hits.iloc[0]["source"] == SOURCE_SMOKE
    ctrl = known_drug_positive_control(hits, "er_high")
    assert ctrl["passed"] is True


def test_dose_curves_are_sampled_points_not_solver_params():
    curve = sample_dose_curve(250.0, cmax_nm=250.0)
    assert "concentration_nm" in curve and "viability" in curve
    assert curve["measured"] is True
    assert curve["simulation"] is False
    y = hill_viability(np.array([250.0]), 250.0)[0]
    assert abs(y - 0.5) < 1e-6


def test_nearest_line_concordance_threshold():
    pairs = [("LumA", "LumA")] * 6 + [("LumA", "Basal")] * 2
    rec = subtype_concordance(pairs, chance=0.33)
    assert rec["passed"] is True
    lines = nearest_lines(np.array([1.0, 0.0]), np.array([[1.0, 0.0], [0.0, 1.0]]), ["MCF7", "MDAMB231"], k=1)
    assert lines[0]["line_id"] == "MCF7"
    assert len(lines[0]["fingerprint"]) == 5


def test_payload_split_encoder_and_state3(tmp_path, monkeypatch):
    cohort, patients = assemble_v3(encoder="linear_poe", n=90, n_boot=8)
    assert cohort["encoder"] == "linear_poe"
    assert glossary_allows_nll("linear_poe") is False
    assert glossary_allows_nll("jax_poe_vae") is True
    abstain = patients["TCGA-A1-A0SK"]
    assert abstain["state"] == 3
    assert abstain["reversal_candidates"] is None
    assert abstain["prognostic_estimate"] is None
    assert abstain["nearest_lines"] is None
    assert validate_patient(abstain, cohort) == []
    full = patients["TCGA-A8-A081"]
    assert full["reversal_candidates"]["order_carries_no_meaning"] is True
    assert_safe(full["prognostic_estimate"]["label"])
    with pytest.raises(ValueError):
        assert_safe("predicted survival is 12 months")


def test_a1_failure_does_not_force_k():
    rec = freeze_preregistered_k(3, {"bic": 1, "silhouette": 0.1, "stability": 0.2}, clustering_available=False)
    assert rec["k"] is None
    assert rec["clustering_available"] is False


def test_persist_smoke_writes_app_payloads(tmp_path):
    v2 = tmp_path / "v2"
    (v2 / "src").mkdir(parents=True)
    repo = tmp_path
    (repo / "application" / "apps" / "api" / "app" / "data").mkdir(parents=True)
    # assemble writes using real helpers; point v3_interim at tmp by using a fake root with src/gate.py
    (v2 / "src" / "gate.py").write_text("# stub\n")
    out = persist_smoke(v2, repo_root=repo)
    assert out["n_patients"] == 3
    assert (repo / "application" / "apps" / "api" / "app" / "data" / "v3" / "cohort_payload.json").is_file()
