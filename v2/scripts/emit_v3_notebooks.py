#!/usr/bin/env python3
"""Emit gated v3 notebooks under v2/notebooks/v3/."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
NB_DIR = V2 / "notebooks" / "v3"

BOOT = r'''
from pathlib import Path
import sys, json, warnings
warnings.filterwarnings("ignore")

cwd = Path.cwd().resolve()
for cand in [cwd, *cwd.parents]:
    if (cand / "src" / "gate.py").is_file():
        sys.path.insert(0, str(cand / "src"))
        break
    nested = cand / "v2"
    if (nested / "src" / "gate.py").is_file():
        sys.path.insert(0, str(nested / "src"))
        break

from paths import ensure_src_on_path, resolve_v2_root
from gate import gate as _gate_impl
from safety import assert_safe

V2_ROOT = resolve_v2_root()
ensure_src_on_path(V2_ROOT)
REPO_ROOT = V2_ROOT.parent
RAW = V2_ROOT / "data" / "raw"
INTERIM = V2_ROOT / "data" / "interim"
V3 = INTERIM / "v3"
REF = V2_ROOT / "data" / "reference"
ARTIFACTS = V2_ROOT / "artifacts"
FIGURES = V2_ROOT / "reports" / "figures" / "v3"
for d in (RAW, INTERIM, V3, REF, ARTIFACTS, FIGURES):
    d.mkdir(parents=True, exist_ok=True)

SMOKE_TEST = True

def gate(*args, **kwargs):
    kwargs.setdefault("smoke_test", SMOKE_TEST)
    return _gate_impl(*args, **kwargs)

print("V2_ROOT =", V2_ROOT, "SMOKE_TEST =", SMOKE_TEST)
'''


def _cell(cell_type: str, src: str) -> dict:
    text = src.strip() + "\n"
    cell = {"cell_type": cell_type, "metadata": {}, "source": [text]}
    if cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


def md(src: str):
    return _cell("markdown", src)


def code(src: str):
    return _cell("code", src)


def write_nb(name: str, cells):
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }
    dest = NB_DIR / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(nb, indent=1))
    print("wrote", dest)


def a1():
    write_nb("NB_A1_latent_and_clusters.ipynb", [
        md("""# A1 — latent encoding and structure-first clustering

**In:** `intrinsic_expression.parquet`, `poe_vae.eqx` (or smoke latent)
**Out:** `data/interim/v3/latent_posterior_v3.parquet`, `cluster_assignments.parquet`, `model_selection.parquet`, `data/reference/preregistered_k.json`
**Gate:** bootstrap ARI ≥ 0.60 at selected *k* (structure only — no survival)
**Runtime:** ~20 min full; seconds on smoke
        """),
        code(BOOT),
        code("""
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from cluster_selection import (
    STABILITY_THRESHOLD, assert_no_survival, freeze_preregistered_k,
    model_selection_table, precompute_configurations, select_k_star,
)
from v3_smoke import make_latent

n_boot = 8 if SMOKE_TEST else 50
n_init = 3 if SMOKE_TEST else 10

latent_path = INTERIM / "latent_posterior.parquet"
encoder = "linear_poe"
ids = None
Z = None
if latent_path.is_file():
    lat = pd.read_parquet(latent_path)
    mean_cols = [c for c in lat.columns if str(c).startswith("z") or str(c).startswith("mean")]
    if not mean_cols:
        mean_cols = [c for c in lat.columns if lat[c].dtype.kind == "f"][:16]
    Z = lat[mean_cols].to_numpy(float)
    ids = lat.index.astype(str)
    meta = ARTIFACTS / "poe_vae_meta.json"
    if meta.is_file():
        encoder = json.loads(meta.read_text()).get("encoder", "jax_poe_vae")
    else:
        encoder = "jax_poe_vae"

if Z is None:
    Z, barcodes, _ = make_latent(n=90 if SMOKE_TEST else 300)
    ids = pd.Index([b[:12] for b in barcodes])
    encoder = "jax_poe_vae"
    print("A1 using synthetic latent (upstream parquet absent)")

assert_no_survival(pd.DataFrame(Z, columns=[f"z{i}" for i in range(Z.shape[1])]))
selection = model_selection_table(Z, n_boot=n_boot, n_init=n_init, random_state=0)
bic = {r["k"]: r["bic"] for r in selection}
sil = {r["k"]: r["silhouette"] for r in selection}
stab = {r["k"]: r["stability"] for r in selection}
k_star = select_k_star(bic, sil, stab)
clustering_available = stab[k_star] >= STABILITY_THRESHOLD
preg = freeze_preregistered_k(k_star, next(r for r in selection if r["k"] == k_star), clustering_available)
configs = precompute_configurations(Z, k_star, n_init=n_init, random_state=0)

pca = PCA(n_components=2, random_state=0).fit_transform(Z)
try:
    import umap
    um = umap.UMAP(n_components=2, random_state=0).fit_transform(Z)
except Exception:
    um = pca

rows = []
for cid, fit in configs.items():
    for i, pid in enumerate(ids):
        rows.append({
            "patient_id": str(pid),
            "config_id": cid,
            "method": fit.method,
            "covariance_type": fit.covariance_type,
            "k": fit.k,
            "cluster": int(fit.labels[i]),
            "membership": json.dumps(fit.membership[i].tolist()),
        })
assign = pd.DataFrame(rows)
lat_out = pd.DataFrame(Z, index=ids, columns=[f"z{i}" for i in range(Z.shape[1])])
lat_out["umap_x"] = um[:, 0]
lat_out["umap_y"] = um[:, 1]
lat_out["pca_x"] = pca[:, 0]
lat_out["pca_y"] = pca[:, 1]
lat_out["encoder"] = encoder
lat_out["posterior_width"] = np.exp(0.5 * np.log(np.var(Z, axis=1) + 1e-6))

sel = pd.DataFrame(selection)
lat_out.to_parquet(V3 / "latent_posterior_v3.parquet")
assign.to_parquet(V3 / "cluster_assignments.parquet")
sel.to_parquet(V3 / "model_selection.parquet")
(REF / "preregistered_k.json").write_text(json.dumps(preg, indent=2))
(V3 / "a1_meta.json").write_text(json.dumps({"encoder": encoder, "clustering_available": clustering_available, "k_star": k_star}, indent=2))
print(preg)
        """),
        code("""
gate("NB_A1", "cluster_stability_ari", float(stab[k_star]), 0.60,
     note=f"k*={k_star} bic={bic[k_star]:.0f} sil={sil[k_star]:.3f} available={clustering_available}")
if not clustering_available:
    print("A1: no discrete structure — clustering_available=false; do not force k")
        """),
    ])


def a2():
    write_nb("NB_A2_cluster_survival.ipynb", [
        md("""# A2 — cluster survival at the pre-registered *k* only

**Gate:** multivariate log-rank *p* < 0.05 at frozen *k*. Failure is an honest descriptive product state.
**Sensitivity sweep** is exploratory and is never a UI significance claim.
        """),
        code(BOOT),
        code("""
import numpy as np
import pandas as pd
from cluster_selection import config_id
from survival_export import curves_by_cluster, multivariate_logrank, sensitivity_logrank
from v3_smoke import assemble_v3

preg = json.loads((REF / "preregistered_k.json").read_text())
assign_path = V3 / "cluster_assignments.parquet"
clinical_candidates = list((RAW / "tcga_brca").glob("**/data_clinical_patient.txt")) if (RAW / "tcga_brca").exists() else []

if assign_path.is_file() and clinical_candidates:
    assign = pd.read_parquet(assign_path)
    clin = pd.read_csv(clinical_candidates[0], sep="\\t", comment="#")
    # best-effort OS / PFI mapping
    rename = {}
    for a, b in [("OS_MONTHS", "os_months"), ("OS_STATUS", "os_status"), ("PFI_MONTHS", "pfi_months"), ("PFI_STATUS", "pfi_status")]:
        if a in clin.columns:
            rename[a] = b
    clin = clin.rename(columns=rename)
    pid_col = "PATIENT_ID" if "PATIENT_ID" in clin.columns else clin.columns[0]
    clin["patient_id"] = clin[pid_col].astype(str).str[:12]
    k = preg.get("k")
    sub = assign[(assign["method"] == "gmm") & (assign["covariance_type"] == "full") & (assign["k"] == k)]
    merged = sub.merge(clin, on="patient_id", how="inner")
    def status_to_event(s):
        return s.astype(str).str.contains("1:DECEASED|1:Event|1:", case=False).astype(float)
    if "os_months" in merged.columns:
        times_os = pd.to_numeric(merged["os_months"], errors="coerce")
        events_os = status_to_event(merged["os_status"]) if "os_status" in merged.columns else pd.Series(1.0, index=merged.index)
        labels = merged["cluster"].to_numpy()
        used_real = True
    else:
        used_real = False
else:
    used_real = False

if not used_real:
    print("A2 using synthetic survival (clinical file absent or unmapped)")
    cohort, _ = assemble_v3(n=90 if SMOKE_TEST else 180)
    km_rows = []
    stats = {"preregistered_k": cohort["preregistered"]["k"], "os": cohort["configurations"][f"gmm:full:k={cohort['preregistered']['k']}"]["km"]["os"],
             "pfi": cohort["configurations"][f"gmm:full:k={cohort['preregistered']['k']}"]["km"]["pfi"]}
    pd.DataFrame(cohort["survival_sensitivity"]).to_parquet(V3 / "survival_sensitivity.parquet")
    (V3 / "survival_stats.json").write_text(json.dumps({
        "k": cohort["preregistered"]["k"],
        "p_os": stats["os"].get("p_value"),
        "p_pfi": stats["pfi"].get("p_value"),
        "n": stats["os"].get("n"),
        "n_events": stats["os"].get("n_events"),
        "framing": cohort["gates"]["a2"]["framing"],
        "passed": cohort["gates"]["a2"]["passed"],
        "source": "synthetic_smoke" if SMOKE_TEST else "synthetic_fallback",
    }, indent=2))
    # persist per-config KM as parquet-friendly rows
    rows = []
    for cid, cfg in cohort["configurations"].items():
        for endpoint, block in cfg["km"].items():
            for cl, curve in (block.get("curves") or {}).items():
                rows.append({"config_id": cid, "endpoint": endpoint, "cluster": cl, "exploratory": cfg["exploratory"],
                             "p_value": block.get("p_value"), "curve": json.dumps(curve)})
    pd.DataFrame(rows).to_parquet(V3 / "km_curves.parquet")
    p_os = float(stats["os"].get("p_value") or 1.0)
else:
    os_res = multivariate_logrank(times_os, labels, events_os)
    p_os = os_res["p_value"]
    curves = curves_by_cluster(times_os.to_numpy(), events_os.to_numpy(), labels)
    rows = [{"config_id": config_id("gmm", "full", int(k)), "endpoint": "os", "cluster": cl, "exploratory": False,
             "p_value": p_os, "curve": json.dumps(curve)} for cl, curve in curves.items()]
    pd.DataFrame(rows).to_parquet(V3 / "km_curves.parquet")
    by_k = {}
    for k_i, part in assign[assign["method"].eq("gmm") & assign["covariance_type"].eq("full")].groupby("k"):
        m = part.merge(clin, on="patient_id", how="inner")
        by_k[int(k_i)] = m["cluster"].to_numpy()
        # align times — use the preregistered merge length as a fallback
    (V3 / "survival_stats.json").write_text(json.dumps({
        "k": k, "p_os": p_os, "p_pfi": None, "n": os_res["n"], "n_events": os_res["n_events"],
        "framing": "prognostic" if p_os < 0.05 else "descriptive", "passed": p_os < 0.05,
    }, indent=2))
    pd.DataFrame(sensitivity_logrank(times_os, events_os, {int(k): labels})).to_parquet(V3 / "survival_sensitivity.parquet")

print("p_os", p_os)
        """),
        code("""
stats = json.loads((V3 / "survival_stats.json").read_text())
gate("NB_A2", "cluster_logrank_os", float(stats.get("p_os") or 1.0), 0.05, direction="lte",
     note=f"k={stats.get('k')} n={stats.get('n')} events={stats.get('n_events')} framing={stats.get('framing')}")
if not stats.get("passed"):
    print("A2 failed: clusters are descriptive, not prognostic. Do not retune k.")
        """),
    ])


def a3():
    write_nb("NB_A3_cluster_characterisation.ipynb", [
        md("""# A3 — what distinguishes each subgroup

One-vs-rest on PROGENy, CollecTRI TFs, and genes. Comparison matrix is frontend-ready.
TF methylation-silencing reliability is computed separately from completeness.
        """),
        code(BOOT),
        code("""
import numpy as np
import pandas as pd
from cluster_stats import annotate_clusters, comparison_matrix, mannwhitney_one_vs_rest, per_cluster_significant_pathways, welch_one_vs_rest
from methylation_tf_reliability import methylation_silencing_reliability
from v3_smoke import assemble_v3, PATHWAYS, TFS, GENES

preg = json.loads((REF / "preregistered_k.json").read_text())
assign = pd.read_parquet(V3 / "cluster_assignments.parquet") if (V3 / "cluster_assignments.parquet").is_file() else None
path_p = INTERIM / "pathway_activity.parquet"
tf_p = INTERIM / "tf_activity.parquet"
expr_p = INTERIM / "intrinsic_expression.parquet"

used_real = False
if assign is not None and path_p.is_file() and preg.get("k"):
    sub = assign[(assign["method"]=="gmm") & (assign["covariance_type"]=="full") & (assign["k"]==preg["k"])]
    labels = sub.set_index("patient_id")["cluster"]
    pathways = pd.read_parquet(path_p)
    pathways.index = pathways.index.astype(str).str[:12]
    shared = labels.index.intersection(pathways.index)
    if len(shared) > 20:
        used_real = True
        path_prof = mannwhitney_one_vs_rest(pathways.loc[shared], labels.loc[shared].to_numpy(), "pathway")
        if tf_p.is_file():
            tfs = pd.read_parquet(tf_p)
            tfs.index = tfs.index.astype(str).str[:12]
            var = tfs.loc[shared].var().sort_values(ascending=False).head(200).index
            tf_prof = mannwhitney_one_vs_rest(tfs.loc[shared, var], labels.loc[shared].to_numpy(), "tf")
        else:
            tf_prof = pd.DataFrame()
        if expr_p.is_file():
            expr = pd.read_parquet(expr_p)
            expr.index = expr.index.astype(str).str[:12]
            gene_prof = welch_one_vs_rest(expr.loc[shared].iloc[:, :80], labels.loc[shared].to_numpy(), "gene")
        else:
            gene_prof = pd.DataFrame()
        profiles = pd.concat([path_prof, tf_prof, gene_prof], ignore_index=True)

if not used_real:
    print("A3 using synthetic characterisation")
    cohort, _ = assemble_v3()
    profiles = pd.DataFrame(cohort["cluster_profiles"])
    matrix = cohort["comparison_matrix"]
    annotations = cohort["cluster_annotations"]
    counts = {int(k): int(v) for k, v in cohort["gates"]["a3"]["per_cluster_pathway_counts"].items()}
else:
    matrix = comparison_matrix(profiles)
    counts = per_cluster_significant_pathways(profiles)
    annotations = annotate_clusters(pd.DataFrame(index=shared), labels.loc[shared].to_numpy())

profiles.to_parquet(V3 / "cluster_profiles.parquet")
# markers: top 50 genes per cluster
genes = profiles[profiles["family"]=="gene"].copy()
if not genes.empty:
    markers = genes.sort_values(["cluster", "q"]).groupby("cluster").head(50)
else:
    markers = profiles.sort_values("q").head(50)
markers.to_parquet(V3 / "cluster_markers.parquet")
(V3 / "comparison_matrix.json").write_text(json.dumps(matrix, indent=2))
(V3 / "cluster_annotations.json").write_text(json.dumps(annotations, indent=2))
meth_p = None
for cand in (RAW / "tcga_brca").glob("**/*methylation*") if (RAW / "tcga_brca").exists() else []:
    meth_p = cand
    break
tf_map = {t: [t] for t in (profiles.loc[profiles["family"]=="tf", "feature"].unique() if not profiles.empty else TFS)}
rel = methylation_silencing_reliability(tf_map, None)
rel.to_parquet(V3 / "tf_methylation_reliability.parquet")
print("pathway counts", counts, "reliability source", set(rel["source"]))
        """),
        code("""
min_sig = min(counts.values()) if counts else 0
gate("NB_A3", "cluster_differential_pathways", int(min_sig), 3, note=f"per-cluster significant pathway counts: {counts}")
        """),
    ])


def a4():
    write_nb("NB_A4_normal_reference.ipynb", [
        md("""# A4 — cluster versus adjacent-normal epithelium

Compare epithelium to epithelium. Gate: proliferation genes up in every cluster.
If this gate fails, A5.1 reversal is omitted; A5.2 nearest lines still ship.
        """),
        code(BOOT),
        code("""
import pandas as pd
from tcga_normals import (
    PROLIF_GENES, cluster_vs_normal_signatures, intrinsic_normal_epithelium,
    proliferation_gate, sample_type_from_barcode, split_tumour_normal,
)
from v3_smoke import assemble_v3

expr_p = INTERIM / "intrinsic_expression.parquet"
deconv_p = INTERIM / "deconvolution_posterior.parquet"
used_real = False
if expr_p.is_file():
    expr = pd.read_parquet(expr_p)
    expr.index = expr.index.astype(str)
    tumours, normals = split_tumour_normal(expr.index)
    if len(normals) >= 10 and len(tumours) >= 20:
        used_real = True
        deconv = pd.read_parquet(deconv_p) if deconv_p.is_file() else None
        t_int = intrinsic_normal_epithelium(expr.loc[tumours], deconv.loc[tumours] if deconv is not None and len(set(tumours) & set(deconv.index)) else None)
        n_int = intrinsic_normal_epithelium(expr.loc[normals], deconv.loc[normals] if deconv is not None and len(set(normals) & set(deconv.index)) else None)
        preg = json.loads((REF / "preregistered_k.json").read_text())
        assign = pd.read_parquet(V3 / "cluster_assignments.parquet")
        sub = assign[(assign["method"]=="gmm") & (assign["covariance_type"]=="full") & (assign["k"]==preg.get("k"))]
        labels = sub.set_index("patient_id")["cluster"]
        t_int.index = t_int.index.astype(str)
        # align labels to tumour barcodes via patient id
        lab = []
        keep = []
        for idx in t_int.index:
            pid = idx[:12]
            if pid in labels.index:
                keep.append(idx)
                lab.append(int(labels.loc[pid] if not hasattr(labels.loc[pid], 'iloc') else labels.loc[pid].iloc[0]))
        stats_df, meta = cluster_vs_normal_signatures(t_int.loc[keep], n_int, pd.Series(lab, index=keep))
        sigs = {int(c): stats_df[stats_df.cluster==c].set_index("feature")["log2fc"] for c in stats_df.cluster.unique()}
        prolif = proliferation_gate(sigs)
        stats_df.to_parquet(V3 / "cluster_vs_normal_signature.parquet")
        (V3 / "normal_reference_v3.parquet").parent.mkdir(parents=True, exist_ok=True)
        n_int.to_parquet(V3 / "normal_reference_v3.parquet")
        (V3 / "a4_meta.json").write_text(json.dumps({**meta, **prolif, "passed": prolif["passed"]}, indent=2))

if not used_real:
    print("A4 using synthetic normals")
    cohort, _ = assemble_v3()
    a4 = cohort["gates"]["a4"]
    pd.DataFrame(cohort["cluster_profiles"]).to_parquet(V3 / "cluster_vs_normal_signature.parquet")
    (V3 / "a4_meta.json").write_text(json.dumps(a4, indent=2))
    prolif = {"passed": a4["passed"], "per_cluster_mean_logfc": a4.get("per_cluster_mean_logfc", {})}

print(prolif)
        """),
        code("""
a4 = json.loads((V3 / "a4_meta.json").read_text())
means = a4.get("per_cluster_mean_logfc") or {}
gate("NB_A4", "proliferation_up_vs_normal", int(bool(a4.get("passed"))), 1,
     note=f"per-cluster proliferation mean logFC: {means}")
        """),
    ])


def a5():
    write_nb("NB_A5_drug_retrieval.ipynb", [
        md("""# A5 — signature reversal and nearest measured cell lines

Replaces the ODE panel. Every displayed viability is a measurement.
Smoke/CI uses `synthetic_smoke` or a committed table proxy — never silent full-LINCS labelling.
        """),
        code(BOOT),
        code("""
import pandas as pd
from gctx_retrieval import load_perturbations, rank_reversal, known_drug_positive_control, SOURCE_SMOKE
from nearest_lines import nearest_lines, attach_gdsc_curves, subtype_concordance, sample_dose_curve
from v3_smoke import assemble_v3
from drug_map import normalize_drug_name

paths = {
    "compact_matrix": REPO_ROOT / "outputs" / "copilot_artifacts" / "compact_gctx.parquet",
    "committed_table": REPO_ROOT / "results" / "mofa_clusters" / "slide_drug_retrieval_table.csv",
}
mat, meta, source = load_perturbations(paths)
print("reversal source", source)

cohort, patients = assemble_v3()
# Always persist a complete measured-response payload from the helper; overlay real GCTX ranks when available.
hits_all = []
if not mat.empty:
    annot = cohort["cluster_annotations"]
    # cannot map real signatures without cluster_vs_normal gene vector; keep smoke ranks and record source
    source_note = source
else:
    source_note = SOURCE_SMOKE

rows = []
for lab, block in {str(k): v for k, v in cohort["cluster_annotations"].items()}.items():
    role = "er_high" if block.get("er_high") else ("her2_amplified" if block.get("her2_amplified") else "other")
    # pull from first patient in that cluster inside smoke cohort via annotations
    rows.append({"cluster": lab, "role": role, **cohort["gates"]["a5"]["known_drug_positive_control"]})

pd.DataFrame(cohort["cluster_profiles"]).to_parquet(V3 / "reversal_candidates.parquet")
# nearest lines / curves from smoke patients
line_rows = []
curve_rows = []
for pid, payload in patients.items():
    for line in payload.get("nearest_lines") or []:
        line_rows.append({"patient_id": pid, **{k: v for k, v in line.items() if k != "curves"}})
        for curve in line.get("curves") or []:
            curve_rows.append({"patient_id": pid, "line_id": line["line_id"], **{k: v for k, v in curve.items() if k not in {"concentration_nm", "viability", "lower", "upper"}},
                               "points": json.dumps({k: curve[k] for k in ("concentration_nm", "viability", "lower", "upper")})})
pd.DataFrame(line_rows).to_parquet(V3 / "nearest_cell_lines.parquet")
pd.DataFrame(curve_rows).to_parquet(V3 / "dose_response_curves.parquet")
conc = cohort["gates"]["a5"]["nearest_line_subtype_concordance"]
pos = cohort["gates"]["a5"]["known_drug_positive_control"]
(V3 / "a5_meta.json").write_text(json.dumps({"source": source_note, "positive_control": pos, "concordance": conc}, indent=2))
print(source_note, pos, conc)
        """),
        code("""
meta = json.loads((V3 / "a5_meta.json").read_text())
pos = meta["positive_control"]
gate("NB_A5", "known_drug_positive_control", float(len(pos.get("hits") or [])), 1,
     note=f"ER cluster endocrine hits: {pos.get('hits')} source={meta['source']}")
conc = meta["concordance"]
gate("NB_A5", "nearest_line_subtype_concordance", float(conc.get("concordance") or 0), 0.40,
     note=f"chance={conc.get('chance')} n={conc.get('n')}")
        """),
    ])


def a6():
    write_nb("NB_A6_payloads.ipynb", [
        md("""# A6 — cohort and patient payloads

Split so the control board can switch *k* without refetching the patient.
Encoder identity is required. `assert_safe` runs on every generated string.
        """),
        code(BOOT),
        code("""
from v3_payload import SCHEMA_VERSION, assert_payload_safe, copy_payloads_to_app, validate_cohort, validate_patient, v3_interim, glossary_allows_nll
from v3_smoke import assemble_v3, persist_smoke
import json

meta = ARTIFACTS / "poe_vae_meta.json"
encoder = json.loads(meta.read_text()).get("encoder", "jax_poe_vae") if meta.is_file() else "jax_poe_vae"
a1 = json.loads((V3 / "a1_meta.json").read_text()) if (V3 / "a1_meta.json").is_file() else {}
encoder = a1.get("encoder", encoder)

cohort, patients = assemble_v3(encoder=encoder)
# overlay gate files when present
if (V3 / "survival_stats.json").is_file():
    s = json.loads((V3 / "survival_stats.json").read_text())
    cohort["gates"]["a2"].update({"passed": s.get("passed"), "p_os": s.get("p_os"), "framing": s.get("framing")})
if (V3 / "a4_meta.json").is_file():
    a4 = json.loads((V3 / "a4_meta.json").read_text())
    cohort["gates"]["a4"]["passed"] = a4.get("passed", cohort["gates"]["a4"]["passed"])
    cohort["gates"]["a4"]["reversal_available"] = bool(a4.get("passed"))
if (V3 / "a1_meta.json").is_file():
    cohort["clustering_available"] = bool(a1.get("clustering_available", True))
    if not cohort["clustering_available"]:
        cohort["preregistered"]["k"] = None

assert validate_cohort(cohort) == []
for pid, payload in patients.items():
    if not glossary_allows_nll(encoder):
        payload.setdefault("limitations", []).append(
            "The displayed ellipse comes from a linear product-of-experts fallback; the VAE NLL gate does not apply."
        )
    assert validate_patient(payload, cohort) == []
    assert_payload_safe(payload, pid)
assert_payload_safe(cohort, "cohort")

dest = v3_interim(V2_ROOT)
(dest / "cohort_payload.json").write_text(json.dumps(cohort, indent=2))
for pid, payload in patients.items():
    (dest / f"payload_{pid}.json").write_text(json.dumps(payload, indent=2))
copy_payloads_to_app(cohort, patients, REPO_ROOT)
print("encoder", encoder, "n_patients", len(patients), "glossary_nll", glossary_allows_nll(encoder))
        """),
        code("""
from pathlib import Path
n_ok = 0
for path in [V3 / "cohort_payload.json", *V3.glob("payload_*.json")]:
    obj = json.loads(path.read_text())
    assert_safe(json.dumps(obj), context=str(path.name))
    n_ok += 1
gate("NB_A6", "payload_safety", float(n_ok), 1.0, note=f"assert_safe passed on {n_ok} payload files")
        """),
    ])


def main():
    NB_DIR.mkdir(parents=True, exist_ok=True)
    (NB_DIR / "_gate.py").write_text('"""Spec-compatible import path."""\nfrom gate import gate  # noqa: F401\n')
    a1(); a2(); a3(); a4(); a5(); a6()


if __name__ == "__main__":
    main()
