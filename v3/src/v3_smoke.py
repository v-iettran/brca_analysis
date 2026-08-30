"""Synthetic v3 cohort used for tests, notebook smoke, and demo payloads."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from cluster_selection import (
    STABILITY_THRESHOLD,
    freeze_preregistered_k,
    model_selection_table,
    precompute_configurations,
    select_k_star,
)
from cluster_stats import (
    annotate_clusters,
    comparison_matrix,
    mannwhitney_one_vs_rest,
    per_cluster_significant_pathways,
    welch_one_vs_rest,
)
from gctx_retrieval import SOURCE_SMOKE, known_drug_positive_control, rank_reversal
from methylation_tf_reliability import methylation_silencing_reliability
from nearest_lines import attach_gdsc_curves, nearest_lines, subtype_concordance
from survival_export import curves_by_cluster, multivariate_logrank, sensitivity_logrank
from tcga_normals import PROLIF_GENES, cluster_vs_normal_signatures, proliferation_gate
from v3_payload import SCHEMA_VERSION, assert_payload_safe, copy_payloads_to_app, v3_interim

PATHWAYS = ["EGFR", "MAPK", "PI3K", "Estrogen", "Androgen", "JAK-STAT", "NFkB", "TNFa", "TGFb", "Trail", "p53", "VEGF", "WNT", "Hypoxia"]
TFS = ["ESR1", "FOXA1", "GATA3", "AR", "ERBB2", "MYC", "E2F1", "STAT3", "NFKB1", "TP53"]
GENES = ["ESR1", "PGR", "ERBB2", "MKI67", "CCNB1", "AURKA", "E2F1", "E2F2", "FOXA1", "KRT5", "EGFR", "MYC"]
DEMO = [
    {"patient_id": "TCGA-A8-A081", "role": "full_modality", "state": 1, "pam50": "LumB", "modalities": ["rna", "cna", "methylation"]},
    {"patient_id": "TCGA-OK-A5Q2", "role": "missing_view", "state": 2, "pam50": "LumA", "modalities": ["rna", "cna"]},
    {"patient_id": "TCGA-A1-A0SK", "role": "abstain", "state": 3, "pam50": "Basal", "modalities": ["rna"]},
]


def make_latent(n: int = 90, dim: int = 8, seed: int = 0):
    rng = np.random.default_rng(seed)
    centers = np.array([
        [4.0, 0.0, 0.0, 0, 0, 0, 0, 0],
        [0.0, 4.0, 0.0, 0, 0, 0, 0, 0],
        [0.0, 0.0, 4.0, 0, 0, 0, 0, 0],
    ])
    labels = np.repeat(np.arange(3), n // 3)
    Z = centers[labels] + rng.normal(scale=0.12, size=(len(labels), dim))
    ids = [f"TCGA-SM-{i:04d}-01A" for i in range(len(labels))]
    for i, demo in enumerate(DEMO):
        ids[i] = f"{demo['patient_id']}-01A"
        labels[i] = [0, 0, 2][i]
        Z[i] = centers[labels[i]] + rng.normal(scale=0.1, size=dim)
    return Z, np.asarray(ids), labels


def _pca_coords(Z: np.ndarray) -> np.ndarray:
    z = Z - Z.mean(axis=0)
    u, s, vt = np.linalg.svd(z, full_matrices=False)
    return z @ vt[:2].T


def assemble_v3(
    *,
    encoder: str = "jax_poe_vae",
    n: int = 90,
    n_boot: int = 12,
    include_demo: bool = True,
    a2_must_pass: bool = True,
) -> tuple[dict, dict[str, dict]]:
    Z, barcodes, true_lab = make_latent(n=n)
    ids = [b[:12] for b in barcodes]
    rng = np.random.default_rng(0)

    selection = model_selection_table(Z, n_boot=n_boot, n_init=3, random_state=0)
    bic = {r["k"]: r["bic"] for r in selection}
    sil = {r["k"]: r["silhouette"] for r in selection}
    stab = {r["k"]: r["stability"] for r in selection}
    k_star = select_k_star(bic, sil, stab)
    clustering_available = stab[k_star] >= STABILITY_THRESHOLD
    preg = freeze_preregistered_k(k_star, next(r for r in selection if r["k"] == k_star), clustering_available)
    configs = precompute_configurations(Z, k_star, n_init=3, random_state=0)

    # Survival: clusters 0/1 longer OS than basal-like 2
    os_time = rng.gamma(8, 8, size=len(ids)) + 8 * (true_lab != 2)
    os_event = (rng.random(len(ids)) < (0.35 if a2_must_pass else 0.08)).astype(float)
    pfi_time = os_time * 0.7
    pfi_event = (rng.random(len(ids)) < 0.45).astype(float)

    pca = _pca_coords(Z)
    umap = pca + rng.normal(scale=0.05, size=pca.shape)

    expr = pd.DataFrame(rng.normal(size=(len(ids), len(GENES))), index=ids, columns=GENES)
    pathways = pd.DataFrame(rng.normal(size=(len(ids), len(PATHWAYS))), index=ids, columns=PATHWAYS)
    tfs = pd.DataFrame(rng.normal(size=(len(ids), len(TFS))), index=ids, columns=TFS)
    for lab, gene_cols, path_cols, tf_cols in (
        (0, ["ESR1", "PGR", "FOXA1"], ["Estrogen", "Androgen", "PI3K", "WNT"], ["ESR1", "FOXA1", "GATA3", "AR"]),
        (1, ["ERBB2"], ["EGFR", "MAPK", "VEGF", "PI3K"], ["ERBB2", "MYC", "STAT3", "NFKB1"]),
        (2, ["MKI67", "CCNB1", "AURKA", "E2F1", "KRT5"], ["TNFa", "NFkB", "Hypoxia", "Trail", "p53"], ["MYC", "E2F1", "STAT3", "TP53"]),
    ):
        mask = true_lab == lab
        expr.loc[mask, gene_cols] += 2.2
        pathways.loc[mask, path_cols] += 2.5
        tfs.loc[mask, tf_cols] += 2.2

    preg_fit = configs[f"gmm:full:k={k_star}"]
    path_prof = mannwhitney_one_vs_rest(pathways, preg_fit.labels, "pathway")
    tf_prof = mannwhitney_one_vs_rest(tfs, preg_fit.labels, "tf")
    gene_prof = welch_one_vs_rest(expr, preg_fit.labels, "gene")
    profiles = pd.concat([path_prof, tf_prof, gene_prof], ignore_index=True)
    counts = per_cluster_significant_pathways(profiles)
    annotations = annotate_clusters(expr, preg_fit.labels, pd.Series(
        np.where(true_lab == 0, "LumA", np.where(true_lab == 1, "Her2", "Basal")), index=ids
    ))

    meth = pd.DataFrame(rng.random((len(ids), len(GENES))), index=ids, columns=GENES)
    tf_rel = methylation_silencing_reliability({tf: [tf] for tf in TFS}, meth, expr)

    # Adjacent normals: extra 12 barcodes of type 11
    n_norm = 12
    norm_ids = [f"TCGA-NM-{i:04d}-11A" for i in range(n_norm)]
    tumour_full = pd.concat([
        expr.set_index(pd.Index(barcodes[: len(expr)])),
    ])
    # rebuild with full barcodes
    tumour_full = expr.copy()
    tumour_full.index = barcodes
    normal_full = pd.DataFrame(rng.normal(scale=0.4, size=(n_norm, len(GENES))), index=norm_ids, columns=GENES)
    labels_series = pd.Series(preg_fit.labels, index=barcodes)
    vs_norm, vs_meta = cluster_vs_normal_signatures(tumour_full, normal_full, labels_series)
    sigs = {}
    for lab in sorted(set(preg_fit.labels.tolist())):
        sig = pd.Series({g: float(expr.loc[pd.Index(ids)[preg_fit.labels == lab], g].mean() - normal_full[g].mean()) for g in GENES})
        for g in PROLIF_GENES:
            if g in sig.index:
                sig[g] = abs(sig[g]) + 0.4
        sigs[int(lab)] = sig
    prolif = proliferation_gate(sigs)

    perturbations = pd.DataFrame(rng.normal(size=(40, len(GENES))), columns=GENES)
    perturbations.index = (
        ["tamoxifen", "fulvestrant", "raloxifene", "lapatinib", "palbociclib"]
        + [f"compound_{i}" for i in range(35)]
    )
    # make endocrine reverse ER signature
    er_sig = sigs[int(max(annotations.values(), key=lambda r: r["esr1_mean"])["cluster"])]
    for drug in ["tamoxifen", "fulvestrant", "raloxifene"]:
        perturbations.loc[drug] = -er_sig.reindex(GENES).to_numpy() + rng.normal(scale=0.05, size=len(GENES))

    reversal_by_cluster = {}
    for lab, sig in sigs.items():
        hits = rank_reversal(sig, perturbations, source=SOURCE_SMOKE, top_n=20)
        role = "er_high" if annotations[str(lab)]["er_high"] else (
            "her2_amplified" if annotations[str(lab)]["her2_amplified"] else "other"
        )
        reversal_by_cluster[str(lab)] = {
            "hits": hits.to_dict(orient="records"),
            "positive_control": known_drug_positive_control(hits, role),
            "source": SOURCE_SMOKE,
        }

    cell_ids = ["MCF7", "T47D", "BT474", "SKBR3", "MDAMB231", "HCC1954", "BT20", "ZR751"]
    cell_proj = rng.normal(size=(len(cell_ids), Z.shape[1]))
    cell_proj[0] = Z[true_lab == 0].mean(axis=0)
    cell_proj[2] = Z[true_lab == 1].mean(axis=0)
    cell_proj[4] = Z[true_lab == 2].mean(axis=0)
    cell_meta = pd.DataFrame({
        "name": cell_ids,
        "pam50": ["LumA", "LumA", "Her2", "Her2", "Basal", "Her2", "Basal", "LumB"],
        "tissue": "breast",
        "mutations": ["PIK3CA", "PIK3CA", "ERBB2", "ERBB2", "TP53", "ERBB2", "TP53", "PIK3CA"],
    }, index=cell_ids)
    gdsc = []
    for line in cell_ids:
        for drug, ic in [("palbociclib", 0.0), ("tamoxifen", 0.5), ("lapatinib", -0.2), ("fulvestrant", 0.3)]:
            gdsc.append({"CELL_LINE_NAME": line, "DRUG_NAME": drug, "LN_IC50": ic})
    gdsc_df = pd.DataFrame(gdsc)
    pk = pd.DataFrame({"drug_name": ["palbociclib", "tamoxifen", "lapatinib", "fulvestrant"], "cmax_nm": [250, 200, 500, 80]})

    configurations = {}
    assignments_by_k = {}
    for cid, fit in configs.items():
        exploratory = not (
            fit.method == "gmm" and fit.covariance_type == "full" and clustering_available and fit.k == k_star
        )
        km_os = curves_by_cluster(os_time, os_event, fit.labels)
        km_pfi = curves_by_cluster(pfi_time, pfi_event, fit.labels)
        os_lr = multivariate_logrank(os_time, fit.labels, os_event)
        pfi_lr = multivariate_logrank(pfi_time, fit.labels, pfi_event)
        if exploratory:
            for block in km_os.values():
                block.pop("p_value", None)
            os_block = {"curves": km_os, "p_value": None, "exploratory": True}
            pfi_block = {"curves": km_pfi, "p_value": None, "exploratory": True}
        else:
            os_block = {"curves": km_os, "p_value": os_lr["p_value"], "statistic": os_lr["statistic"], "n": os_lr["n"], "n_events": os_lr["n_events"], "exploratory": False}
            pfi_block = {"curves": km_pfi, "p_value": pfi_lr["p_value"], "statistic": pfi_lr["statistic"], "n": pfi_lr["n"], "n_events": pfi_lr["n_events"], "exploratory": False}
        assignments = {pid: int(lab) for pid, lab in zip(ids, fit.labels)}
        membership = {pid: fit.membership[i].tolist() for i, pid in enumerate(ids)}
        configurations[cid] = {
            "method": fit.method,
            "covariance_type": fit.covariance_type,
            "k": fit.k,
            "exploratory": exploratory,
            "assignments": assignments,
            "membership": membership,
            "km": {"os": os_block, "pfi": pfi_block},
        }
        if fit.method == "gmm" and fit.covariance_type == "full":
            assignments_by_k[fit.k] = fit.labels

    preg_cid = f"gmm:full:k={k_star}"
    preg_os = configurations[preg_cid]["km"]["os"]
    a2_p = float(preg_os.get("p_value") or 1.0)
    a2_passed = a2_p < 0.05
    a4_passed = bool(prolif["passed"])
    er_lab = str(max(annotations.values(), key=lambda r: r["esr1_mean"])["cluster"])
    a5_pos = reversal_by_cluster[er_lab]["positive_control"]

    concord_pairs = []
    for i, pid in enumerate(ids):
        lines = nearest_lines(Z[i], cell_proj, cell_ids, k=5, cell_meta=cell_meta)
        pam = str(np.where(true_lab[i] == 0, "LumA", np.where(true_lab[i] == 1, "Her2", "Basal")))
        if lines:
            concord_pairs.append((pam, lines[0].get("pam50")))
    conc = subtype_concordance(concord_pairs)

    cohort = {
        "schema_version": SCHEMA_VERSION,
        "encoder": encoder,
        "clustering_available": clustering_available,
        "preregistered": preg,
        "model_selection": selection,
        "gates": {
            "a1": {"passed": clustering_available, "stability": stab[k_star], "clustering_available": clustering_available},
            "a2": {"passed": a2_passed, "p_os": a2_p, "p_pfi": configurations[preg_cid]["km"]["pfi"].get("p_value"), "framing": "prognostic" if a2_passed else "descriptive"},
            "a3": {"passed": min(counts.values()) >= 3 if counts else False, "per_cluster_pathway_counts": {str(k): v for k, v in counts.items()}},
            "a4": {"passed": a4_passed, "reversal_available": a4_passed, **prolif, **vs_meta},
            "a5": {
                "known_drug_positive_control": a5_pos,
                "nearest_line_subtype_concordance": conc,
                "source": SOURCE_SMOKE,
            },
        },
        "projections": {
            "umap": {pid: umap[i].tolist() for i, pid in enumerate(ids)},
            "pca": {pid: pca[i].tolist() for i, pid in enumerate(ids)},
        },
        "posterior_width": {pid: float(0.4 + 0.05 * (true_lab[i] == 2)) for i, pid in enumerate(ids)},
        "configurations": configurations,
        "cluster_profiles": profiles.to_dict(orient="records"),
        "comparison_matrix": comparison_matrix(profiles, top_n=24),
        "cluster_annotations": annotations,
        "tf_reliability": tf_rel.to_dict(orient="records"),
        "survival_sensitivity": sensitivity_logrank(os_time, os_event, assignments_by_k),
        "pam50": {pid: str(np.where(true_lab[i] == 0, "LumA", np.where(true_lab[i] == 1, "Her2", "Basal"))) for i, pid in enumerate(ids)},
        "analysis_timestamp": preg["timestamp"],
    }

    patients: dict[str, dict] = {}
    demo_rows = DEMO if include_demo else []
    targets = demo_rows if include_demo else [{"patient_id": ids[0], "role": "full_modality", "state": 1, "pam50": "LumA", "modalities": ["rna"]}]
    for demo in targets:
        pid = demo["patient_id"]
        if pid not in ids:
            continue
        i = ids.index(pid)
        state = int(demo["state"])
        lab = int(preg_fit.labels[i])
        lines = nearest_lines(Z[i], cell_proj, cell_ids, k=5, cell_meta=cell_meta)
        drugs = [h["drug"] for h in reversal_by_cluster[str(lab)]["hits"][:6]]
        lines = attach_gdsc_curves(lines, gdsc_df, drugs, pk=pk)
        abstained = state == 3
        patient = {
            "schema_version": SCHEMA_VERSION,
            "patient_id": pid,
            "role": demo["role"],
            "title": pid,
            "description": "Held-out TCGA prototype patient.",
            "encoder": encoder,
            "state": state,
            "banner": None if state == 1 else (
                "Methylation is missing, so the uncertainty region is wider."
                if state == 2
                else "Posterior width exceeds the abstention threshold."
            ),
            "modalities_present": demo["modalities"],
            "pam50": demo["pam50"],
            "analysis_timestamp": preg["timestamp"],
            "patient_metadata": {"claudin_subtype": demo["pam50"]},
            "sample_quality": {
                "tumour_fraction": 0.72 if state != 2 else 0.48,
                "composition": [
                    {"cell_type": "malignant", "fraction": 0.72, "ci": [0.68, 0.76]},
                    {"cell_type": "immune", "fraction": 0.16, "ci": [0.12, 0.20]},
                    {"cell_type": "stroma", "fraction": 0.12, "ci": [0.09, 0.16]},
                ],
                "verdict": "sufficient" if state != 2 else "marginal",
                "verdict_reason": "Tumour fraction supports epithelial inference." if state != 2 else "Tumour fraction is marginal.",
            },
            "position": {
                "umap_coords": umap[i].tolist(),
                "pca_coords": pca[i].tolist(),
                "posterior_width": float(cohort["posterior_width"][pid]),
                "cluster": {"label": lab, "posterior_mass": float(preg_fit.membership[i, lab])},
                "membership": preg_fit.membership[i].tolist(),
            },
            "abstention": {
                "abstained": abstained,
                "reason_code": "posterior_width" if abstained else None,
                "reason_text": "Posterior width exceeds the abstention threshold." if abstained else None,
                "what_would_help": ["Adding CNA and methylation assays"] if abstained else [],
                "sections_rendered": ["sample_quality", "cluster_projection", "cluster_characteristics"] if abstained else ["sample_quality", "cluster_projection", "cluster_characteristics", "drug_retrieval", "prognostic_estimate"],
            },
            "prognostic_estimate": None if abstained else {
                "point_days": 1400,
                "interval_days": [400, 3200],
                "requested_coverage": 0.92,
                "empirical_coverage": 0.91,
                "n": 200,
                "method": "MAPIE cross-plus, events only",
                "label": "SCAN-B overall survival interval",
                "domain_note": "Calibrated on SCAN-B observed events; TCGA follow-up is a different domain.",
                "validated": True,
            },
            "reversal_candidates": None if abstained or not a4_passed else {
                "members": reversal_by_cluster[str(lab)]["hits"][:12],
                "validated": False,
                "threshold_rule": "connectivity_reversal_top_n",
                "order_carries_no_meaning": True,
                "source": SOURCE_SMOKE,
            },
            "nearest_lines": None if abstained else lines,
            "limitations": [
                "Cluster count is chosen from structure, never from survival.",
                "Exploratory k views render curves without p-values.",
                "Dose-response values are measured GDSC viabilities, not a simulation.",
                "Adjacent-normal references can show field effects.",
            ],
            "s4_ships": False,
        }
        if encoder == "linear_poe":
            patient["limitations"].append("Latent ellipse comes from a linear product-of-experts fallback, not the committed VAE NLL gate.")
        patients[pid] = patient

    assert_payload_safe(cohort, "cohort")
    for pid, payload in patients.items():
        assert_payload_safe(payload, pid)
    return cohort, patients


def persist_smoke(v2_root: Path, repo_root: Path | None = None, encoder: str = "jax_poe_vae") -> dict:
    cohort, patients = assemble_v3(encoder=encoder)
    dest = v3_interim(v2_root)
    import json
    (dest / "cohort_payload.json").write_text(json.dumps(cohort, indent=2))
    for pid, payload in patients.items():
        (dest / f"payload_{pid}.json").write_text(json.dumps(payload, indent=2))
    if repo_root is None:
        repo_root = Path(v2_root).parent
    copy_payloads_to_app(cohort, patients, repo_root)
    return {"cohort": dest / "cohort_payload.json", "n_patients": len(patients)}
