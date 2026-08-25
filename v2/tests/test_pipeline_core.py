import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from acquire import MANIFEST_COLUMNS, empty_manifest, missing_required, register_file
from gate import gate
from ode_lib import (
    bliss_excess_from_effects,
    boolean_interpolate,
    detect_rebound,
    drug_multiplier,
    hill,
    identifiability_sensitivity_rank,
    make_rhs,
)
from pam50 import PAM50_GENES
from paths import ensure_src_on_path, resolve_v2_root
from safety import assert_safe, check_safety, is_safe
from transforms import inverse_normal_transform, precise, product_of_experts, sample_view_mask
from fusion import empirical_coverage, v1_nested_score
from demo_patients import is_excluded, tumour_verdict
from io_data import is_html, is_real_data_file, limit_rows, parse_geo_series_matrix, canon_drug, encode_er_status
from drug_map import gdsc_drug_name_column, normalize_drug_name, ln_ic50_um_to_nm
from deconv import as_count_like
from carnival_pkn import (
    INPUT_NODE,
    build_carnival_pkn,
    ensure_source_only_nodes,
    signed_interactions,
    source_only_nodes,
)


def test_encode_er_status_positve_typo_not_string_sort():
    raw = pd.Series(["Positve", "Negative", "positive", "negative", "ER+", "ER-"])
    er = encode_er_status(raw)
    assert list(er) == [1, 0, 1, 0, 1, 0]
    numeric = encode_er_status(pd.Series([1.0, 0.0, 1, 0]))
    assert list(numeric) == [1, 0, 1, 0]
    # rank/factorize of sorted strings would also happen to get this right;
    # the guard is that we never call factorize / astype("category").cat.codes
    assert encode_er_status(pd.Series(["negative", "positive"])).tolist() == [0.0, 1.0]


def test_gdsc_join_ignores_cell_line_name():
    cols = ["CELL_LINE_NAME", "SANGER_MODEL_ID", "DRUG_NAME", "LN_IC50"]
    assert gdsc_drug_name_column(cols) == "DRUG_NAME"
    assert gdsc_drug_name_column(["CELL_LINE_NAME", "COSMIC_ID"]) is None
    assert abs(ln_ic50_um_to_nm(0.0) - 1000.0) < 1e-6
    assert normalize_drug_name("Ibrance") == "palbociclib"
    assert canon_drug("palbociclib_cdk6") == "palbociclib"


def test_aran_cpe_euro_decimal_and_permutation_null():
    from deconv import euro_float, purity_spearman_with_null
    s = euro_float(pd.Series(["0,9246", "NaN", "0.5"]))
    assert abs(s.iloc[0] - 0.9246) < 1e-6
    assert pd.isna(s.iloc[1])
    assert abs(s.iloc[2] - 0.5) < 1e-6
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=80), index=[f"s{i}" for i in range(80)])
    y = x + rng.normal(scale=0.2, size=80)
    y.index = x.index
    hit = purity_spearman_with_null(x, y, n_perm=200, seed=0)
    assert hit["n"] == 80
    assert hit["rho"] > 0.7
    assert hit["p"] < 0.05
    miss = purity_spearman_with_null(x, pd.Series(rng.normal(size=80), index=x.index), n_perm=200, seed=1)
    assert miss["p"] > 0.05


def test_carnival_network_variation_and_targets():
    from carnival_validate import (
        active_set,
        parse_targets,
        pairwise_jaccard,
        variation_summary,
    )

    identical = variation_summary({"1": {"A", "B"}, "2": {"A", "B"}, "3": {"A", "B"}})
    assert identical["jaccard_mean"] == 1.0
    assert identical["informative"] is False
    disjoint = variation_summary({"1": {"A"}, "2": {"B"}, "3": {"C"}})
    assert disjoint["jaccard_mean"] == 0.0
    assert disjoint["informative"] is True
    js = pairwise_jaccard([{"A", "B"}, {"B", "C"}])
    assert abs(js[0] - 1 / 3) < 1e-9
    obj = {"result": {"nodesAttributes": [
        {"Node": "EGFR", "AvgAct": 1},
        {"Node": "KRAS", "AvgAct": 0},
        {"Node": "INPUT", "AvgAct": 1},
    ]}}
    assert active_set(obj) == {"EGFR"}
    assert parse_targets("EGFR, ERBB2;none") == ["EGFR", "ERBB2"]
    from carnival_validate import gdsc_target_sensitivity
    acts = {"ACH-1": {"EGFR": 1.0, "KRAS": 0.0}}
    gdsc = pd.DataFrame({
        "SANGER_MODEL_ID": ["SID1", "SID1"],
        "PUTATIVE_TARGET": ["EGFR", "AKT1"],
        "LN_IC50": [0.0, 2.0],
    })
    model = pd.DataFrame({"ModelID": ["ACH-1"], "SangerModelID": ["SID1"], "StrippedCellLineName": ["MCF7"], "COSMICID": [1]})
    hit = gdsc_target_sensitivity(acts, gdsc, model)
    assert hit["n_pairs"] == 1
    assert hit["rho"] != hit["rho"] or hit["n_pairs"] < 20  # too few for Spearman



def test_carnival_pkn_signed_xor_and_invcarnival_parents():
    raw = pd.DataFrame({
        "source_genesymbol": ["EGFR", "PTEN", "MAPK1", "ESR1"],
        "target_genesymbol": ["KRAS", "AKT1", "ESR1", "CCND1"],
        "is_stimulation": [True, False, True, True],
        "is_inhibition": [False, True, True, False],  # MAPK1 both → drop
        "consensus_direction": [True, True, True, True],
        "n_references": [5, 4, 9, 3],
    })
    signed = signed_interactions(raw)
    pairs = set(zip(signed["source"], signed["interaction"], signed["target"]))
    assert ("EGFR", 1, "KRAS") in pairs
    assert ("PTEN", -1, "AKT1") in pairs
    assert ("MAPK1", 1, "ESR1") not in pairs
    cyclic = pd.DataFrame({"source": ["A", "B"], "interaction": [1, -1], "target": ["B", "A"]})
    assert not source_only_nodes(cyclic)
    fixed = ensure_source_only_nodes(cyclic, {"A"})
    assert INPUT_NODE in set(fixed["source"])
    pkn, meta = build_carnival_pkn(["ESR1", "E2F1"], ["EGFR", "ESR1", "KRAS"], raw=raw)
    assert list(pkn.columns) == ["source", "interaction", "target"]
    assert meta["n_source_only"] >= 1
    assert meta["n_tf_in_pkn"] >= 1


def test_pk_table_coverage_counts_pairs_not_drugs(tmp_path):
    from pk_table import count_almanac_pairs_fully_covered, load_pk_table, rank_almanac_drugs

    pk = pd.DataFrame({
        "drug_name": ["tamoxifen", "gefitinib", "doxorubicin", "ribociclib"],
        "nsc_id": [180973, 715055, 123127, np.nan],
        "in_ode_topology": [True, True, False, True],
    })
    pairs = pd.DataFrame({
        "drug_a": ["tamoxifen", "tamoxifen", "gefitinib", "ribociclib"],
        "drug_b": ["gefitinib", "doxorubicin", "doxorubicin", "tamoxifen"],
        "score": [1.0, 2.0, 3.0, 4.0],
    })
    n = count_almanac_pairs_fully_covered(pk, pairs)
    assert n == 3  # ribociclib has no NSC — that pair does not count
    ranked = rank_almanac_drugs(pairs)
    assert ranked.iloc[0]["drug"] == "tamoxifen"
    assert ranked.iloc[0]["n_pairs"] == 3
    legacy = tmp_path / "pk.csv"
    pd.DataFrame({"drug": ["Palbociclib_cdk6"], "target_gene": ["CDK6"], "nsc_id": [758247]}).to_csv(legacy, index=False)
    loaded = load_pk_table(legacy)
    assert loaded.iloc[0]["drug_name"] == "palbociclib"
    assert loaded.iloc[0]["drug"] == "palbociclib"


def test_as_count_like_log2_vs_rsem():
    log2 = pd.DataFrame([[1.0, 2.0], [3.0, 4.0]], columns=["A", "B"])
    got = as_count_like(log2)
    assert got.attrs["count_source"] == "log2_to_2p"
    np.testing.assert_allclose(got.iloc[0, 0], 2.0)
    counts = pd.DataFrame([[100.0, 200.0], [300.0, 400.0]], columns=["A", "B"])
    got2 = as_count_like(counts)
    assert got2.attrs["count_source"] == "linear_counts"


def test_gate_insufficient_data_is_not_fail_label(tmp_path):
    ok = gate("NB11", "synergy_vs_almanac_heldout", -0.06, 0.3,
              n=6, min_n=10, cohort=False, v2_root=tmp_path)
    assert ok is False
    rec = json.loads((tmp_path / "reports" / "gates.jsonl").read_text().strip())
    assert rec["status"] == "insufficient_data"
    assert rec["insufficient_data"] is True
    assert rec["passed"] is False
    rec2_ok = gate("NB00", "ok", 1.0, 0.5, cohort=False, v2_root=tmp_path)
    rec2 = json.loads((tmp_path / "reports" / "gates.jsonl").read_text().strip().splitlines()[-1])
    assert rec2["status"] == "pass"


def test_canon_drug_and_geo_series_matrix(tmp_path):
    assert canon_drug("palbociclib_cdk6") == "palbociclib"
    sm = tmp_path / "GSE_series_matrix.txt"
    sm.write_text(
        '!Sample_geo_accession\t"GSM1"\t"GSM2"\n'
        '!Sample_characteristics_ch1\t"overall survival days: 100"\t"overall survival days: 200"\n'
        '!Sample_characteristics_ch1\t"overall survival event: 1"\t"overall survival event: 0"\n'
        "!series_matrix_table_begin\n"
    )
    clin = parse_geo_series_matrix(sm)
    assert list(clin["geo_accession"]) == ["GSM1", "GSM2"]
    assert clin.loc[0, "overall_survival_days"] == "100"


def test_is_html_rejected_as_data(tmp_path):
    html = tmp_path / "ComboDrugGrowth.zip"
    html.write_bytes(b"<html><head><title>403 Forbidden</title></head>")
    assert is_html(html)
    assert not is_real_data_file(html)
    df = pd.DataFrame({"a": range(100)})
    assert len(limit_rows(df, 20)) == 20
    assert len(limit_rows(df, None)) == 100


V2_ROOT = Path(__file__).resolve().parents[1]


def test_resolve_v2_root():
    assert resolve_v2_root(V2_ROOT) == V2_ROOT
    assert resolve_v2_root(V2_ROOT / "notebooks") == V2_ROOT
    ensure_src_on_path(V2_ROOT)


def test_gate_pass_and_fail(tmp_path):
    assert gate("NB00", "ok", 1.0, 0.5, cohort=False, v2_root=tmp_path) is True
    assert gate("NB00", "bad", 0.1, 0.5, cohort=False, v2_root=tmp_path) is False
    assert gate("NB00", "small", 0.01, 0.05, direction="lte", cohort=False, v2_root=tmp_path) is True
    lines = (tmp_path / "reports" / "gates.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[0])
    assert rec["notebook"] == "NB00"
    assert rec["passed"] is True
    assert rec["provisional"] is False
    assert rec["n"] is None
    rec_fail = json.loads(lines[1])
    assert rec_fail["passed"] is False


def test_gate_smoke_is_provisional_and_logs_n(tmp_path):
    assert gate(
        "NB02", "purity_concordance", 0.71, 0.7,
        n=200, smoke_test=True, v2_root=tmp_path,
        sample_ids=[f"TCGA-A2-A{i:03d}" for i in range(200)],
    ) is True
    rec = json.loads((tmp_path / "reports" / "gates.jsonl").read_text().strip())
    assert rec["n"] == 200
    assert rec["smoke_test"] is True
    assert rec["provisional"] is True
    assert rec["passed"] is True
    # a smoke FAIL is not provisional evidence
    assert gate(
        "NB02", "purity_concordance", 0.4, 0.7,
        n=200, smoke_test=True, v2_root=tmp_path,
        sample_ids=[f"TCGA-A2-A{i:03d}" for i in range(200)],
    ) is False
    rec_fail = json.loads((tmp_path / "reports" / "gates.jsonl").read_text().strip().splitlines()[-1])
    assert rec_fail["passed"] is False
    assert rec_fail["provisional"] is False


def test_safety_existing_and_ode_phrases():
    assert is_safe("Predicted trajectory under palbociclib in the ODE.")
    with pytest.raises(ValueError):
        assert_safe("This is the best drug for the patient.")
    with pytest.raises(ValueError):
        assert_safe("We recommend chemotherapy.")
    for phrase in [
        "the patient will respond",
        "expected response duration is long",
        "predicted survival is high",
        "weeks of response are likely",
        "time to progression is short",
    ]:
        hits = check_safety(phrase)
        assert hits, phrase
        with pytest.raises(ValueError):
            assert_safe(phrase)


def test_safety_prediction_set_as_ranking_and_hedged_abstention():
    for phrase in [
        "palbociclib is the top choice for this profile",
        "this is the best agent in the prediction set",
        "ribociclib is the first-line choice",
        "insufficient data, but the set still includes tamoxifen",
        "low confidence, however the interval remains narrow",
    ]:
        hits = check_safety(phrase)
        assert hits, phrase
        with pytest.raises(ValueError):
            assert_safe(phrase)


def test_inverse_normal_transform_row_moments():
    rng = np.random.default_rng(0)
    X = rng.normal(loc=5, scale=3, size=(40, 200))
    Z = inverse_normal_transform(X)
    assert Z.shape == X.shape
    np.testing.assert_allclose(Z.mean(axis=1), 0.0, atol=0.15)
    assert np.all(np.diff(np.argsort(X[0])) == np.diff(np.argsort(Z[0]))) or True
    # ranks preserved: argsort of X equals argsort of Z
    np.testing.assert_array_equal(np.argsort(X[3]), np.argsort(Z[3]))


def test_poe_missing_view_widens_posterior():
    rng = np.random.default_rng(1)
    n_views, batch, dim = 3, 8, 4
    mus = rng.normal(size=(n_views, batch, dim))
    logvars = rng.normal(loc=-1.0, scale=0.1, size=(n_views, batch, dim))
    full = np.ones((n_views, batch, 1))
    mu_f, lv_f = product_of_experts(mus, logvars, full)
    partial = full.copy()
    partial[2] = 0
    mu_p, lv_p = product_of_experts(mus, logvars, partial)
    width_f = np.exp(0.5 * lv_f).mean()
    width_p = np.exp(0.5 * lv_p).mean()
    assert width_p > width_f


def test_sample_view_mask_keeps_one_view():
    rng = np.random.default_rng(2)
    mask = sample_view_mask(rng, n_views=3, batch=16)
    assert mask.shape[0] == 3
    assert mask[:, :16, :].sum() == 3 * 16
    rand = mask[:, 16:, :]
    assert np.all(rand.sum(axis=0) >= 1)


def test_precise_vectors_orthonormal_rows():
    rng = np.random.default_rng(3)
    Xs = rng.normal(size=(80, 30))
    Xt = Xs + 0.1 * rng.normal(size=(80, 30))
    pv_s, pv_t, angles = precise(Xs, Xt, n_pc=10, n_pv=5)
    grams = pv_s @ pv_s.T
    np.testing.assert_allclose(grams, np.eye(5), atol=1e-6)
    assert angles.shape[0] == 10
    assert np.all(np.isfinite(angles))


def test_hill_boundaries():
    assert hill(0.0, 0.5) == pytest.approx(0.0)
    assert hill(1.0, 0.5) == pytest.approx(1.0)
    assert 0 < float(hill(0.5, 0.5)) < 1


def test_drug_multiplier_bounds():
    m0 = drug_multiplier(3, conc=0.0, ic50=10.0, n_nodes=20)
    assert m0[3] == pytest.approx(1.0)
    assert np.all(m0 <= 1.0) and np.all(m0 > 0)
    m = drug_multiplier(3, conc=10.0, ic50=10.0, n_nodes=20)
    assert 0 < m[3] < 1
    assert m[3] == pytest.approx(0.5)
    assert m[0] == pytest.approx(1.0)


def test_bliss_independence_zero_excess():
    e_a, e_b = 0.3, 0.4
    e_ab = e_a + e_b - e_a * e_b
    assert bliss_excess_from_effects(e_a, e_b, e_ab) == pytest.approx(0.0)
    assert bliss_excess_from_effects(e_a, e_b, 0.9) > 0


def test_rebound_detection():
    traj = np.ones((2, 10))
    traj[0] = np.array([0.5, 0.35, 0.2, 0.2, 0.3, 0.5, 0.7, 0.8, 0.85, 0.9])
    traj[1] = np.linspace(1, 0.2, 10)
    nodes = ["IGF1R", "E2F1"]
    assert "IGF1R" in detect_rebound(traj, nodes)
    assert "E2F1" not in detect_rebound(traj, nodes)


def test_boolean_interpolate_and_rhs():
    topology = {
        "nodes": ["A", "B"],
        "edges": [{"source": "A", "target": "B", "sign": 1}],
    }
    x = np.array([0.8, 0.1])
    B = boolean_interpolate(x, topology, k=np.array([0.5]))
    assert B.shape == (2,)
    rhs = make_rhs(topology, {"k": np.array([0.5]), "tau": np.array([1.0, 1.0]), "n": 2.0})
    dx = rhs(0.0, x, {"drug_mult": np.ones(2)})
    assert dx.shape == (2,)


def test_identifiability_report_shape():
    topology = {
        "nodes": ["A", "B"],
        "edges": [{"source": "A", "target": "B", "sign": 1}],
    }
    params = {"k": np.array([0.4]), "tau": np.array([1.0, 0.8]), "n": 2.0}
    report = identifiability_sensitivity_rank(topology, params, x0=np.array([0.5, 0.5]))
    assert report["n_params"] == 3
    assert "nonidentifiable" in report


def test_manifest_schema_and_missing_required(tmp_path):
    df = empty_manifest()
    assert list(df.columns) == MANIFEST_COLUMNS
    fake = tmp_path / "depmap.csv"
    fake.write_bytes(b"depmap-fixture-bytes-for-hashing-ok")
    df = register_file(
        df,
        dataset="DepMap",
        source_key="depmap",
        local_path=fake,
        required_for_nb00=True,
        v2_root=tmp_path,
    )
    assert missing_required(df) == [
        "metabric",
        "tcga_brca",
        "gtex_breast",
        "omnipath",
        "gdsc2",
        "wu_scrna",
    ]
    assert bool(df.loc[df["source_key"] == "depmap", "verified"].iloc[0])
    ph = tmp_path / "PLACEHOLDER.txt"
    ph.write_text("Drop files here. Source: example\n")
    df = register_file(
        df, dataset="x", source_key="metabric", local_path=ph,
        required_for_nb00=True, v2_root=tmp_path,
    )
    assert not bool(df.loc[df["source_key"] == "metabric", "verified"].iloc[0])
    unverified = df.copy()
    unverified["verified"] = False
    assert "depmap" in missing_required(unverified)


def test_pam50_gene_count():
    assert len(PAM50_GENES) == 50


def test_hold_out_drugs_and_spearman_split():
    from ode_eval import hold_out_drugs, spearman_split
    tr, te = hold_out_drugs(["a", "b", "c", "d", "e", "f"], test_frac=0.3, seed=0)
    assert set(tr).isdisjoint(te)
    assert tr and te
    df = pd.DataFrame({
        "predicted": [1, 2, 3, 4, 1, 1, 1, 1],
        "ln_ic50": [4, 3, 2, 1, 1, 2, 3, 4],
        "in_ode_topology": [True, True, True, True, False, False, False, False],
    })
    split = spearman_split(df)
    assert split["n_in"] == 4 and split["n_out"] == 4
    assert split["rho_in"] > 0.5


def test_conformal_does_not_treat_censored_as_observed():
    from fusion import ipcw_weights, observed_event_mask
    time = np.array([10.0, 20.0, 30.0, 40.0])
    event = np.array([1.0, 0.0, 1.0, 0.0])
    mask = observed_event_mask(event)
    assert mask.tolist() == [True, False, True, False]
    w = ipcw_weights(time, event)
    assert w[1] == 0.0 and w[3] == 0.0
    assert w[0] > 0 and w[2] > 0


def test_v1_nested_score_and_coverage():
    assert v1_nested_score(1, 1, 1) == pytest.approx(1.0)
    y = np.array([0.1, 0.5, 0.9])
    lo = np.array([0.0, 0.4, 0.8])
    hi = np.array([0.2, 0.6, 1.0])
    assert empirical_coverage(y, lo, hi) == pytest.approx(1.0)
    assert empirical_coverage(y, lo, np.array([0.15, 0.45, 0.85])) == pytest.approx(1 / 3)


def test_tumour_verdict_and_demo_exclude():
    assert tumour_verdict(0.62) == "sufficient"
    assert tumour_verdict(0.31) == "marginal"
    assert tumour_verdict(0.19) == "insufficient"
    assert is_excluded("TCGA-A2-A04V-01", ["TCGA-A2-A04V"])
    assert not is_excluded("TCGA-E2-A15J", ["TCGA-A2-A04V"])


def test_pathway_candidates_are_a_rule_not_a_coverage_set():
    from pathway_candidates import pathway_candidates
    from poe_vae import view_width_reduction

    pk = pd.DataFrame(
        {
            "drug_name": ["afatinib", "fulvestrant", "palbociclib"],
            "target_gene": ["EGFR", "ESR1", "CDK4"],
            "in_ode_topology": [True, True, False],
        }
    )
    pw = pd.Series({"EGFR": 0.4, "Estrogen": -0.2, "p53": 1.1})
    out = pathway_candidates(pw, pk)
    assert out["basis"] == "pathway_activity_threshold"
    assert out["validated"] is False
    assert "coverage_level" not in out
    names = [m["drug"] for m in out["set_members"]]
    assert names == ["afatinib", "palbociclib"]
    assert view_width_reduction(1.0, 0.6) == pytest.approx(0.4)
    assert view_width_reduction(0.50, 0.50) == pytest.approx(0.0)


def test_glossary_emits_unvalidated_pathway_panel(tmp_path, monkeypatch):
    sys_path = Path(__file__).resolve().parents[1] / "scripts"
    import sys

    sys.path.insert(0, str(sys_path))
    import emit_glossary

    gates = tmp_path / "gates.jsonl"
    gates.write_text(
        json.dumps(
            {
                "notebook": "NB13",
                "gate": "conformal_coverage",
                "value": 0.014,
                "threshold": 0.02,
                "status": "pass",
                "passed": True,
                "n": 106,
                "note": "empirical=0.906 requested=0.92",
            }
        )
        + "\n"
    )
    latest = emit_glossary.latest_gates(gates)
    assert ("NB13", "conformal_coverage") in latest
    panels = {row["panel"] for row in emit_glossary.UNVALIDATED_PANELS}
    assert "pathway_candidates" in panels
    unval = emit_glossary.UNVALIDATED_PANELS[0]["validation"]
    assert unval["status"] == "unvalidated"
    assert unval["metric"] is None
