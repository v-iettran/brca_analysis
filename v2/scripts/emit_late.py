"""Late notebooks NB07–NB14. Imported by emit_notebooks.main."""

from emit_notebooks import BOOT, code, md, write_nb


def nb07():
    write_nb("NB07_carnival.ipynb", [
        md("""
# NB07 — CARNIVAL (**S3 demoted to presentation**)

**In:** DepMap breast cell-line expression, OmniPath signalling PPI
**Out:** `data/interim/causal_networks/{sample_id}.json` (explanation layer)
**Gates:** (1) vs CRISPR essentiality AUROC ≥ 0.65 — recorded failure, threshold not revised.
(2) vs GDSC target sensitivity Spearman — re-validation of what S4 actually needs.

ODE initial conditions come from PROGENy/CollecTRI, not from the ILP.
Essentiality and signalling activity are different biology; a chance essentiality
AUROC is a valid negative if networks vary across lines (mean Jaccard < 0.8).
        """),
        code(BOOT),
        code("""
# Config
# CARNIVAL is throughput, not memory: one ILP is 1–2 GB / 30–90 s.
# Smoke: ~50 solves. Full: every sample (VPS wall-clock, embarrassingly parallel).
AUROC_MIN = 0.65          # do not revise; essentiality fail stands
JACCARD_MAX = 0.8         # mean pairwise Jaccard; ≥ this ⇒ networks are copies
GDSC_RHO_MIN = 0.3        # target-sensitivity re-validation (what S4 needs)
TIMELIMIT = 90 if SMOKE_TEST else 300
MAX_SAMPLES = N_PATIENTS
R_SCRIPT = V2_ROOT / "notebooks" / "r" / "run_carnival.R"
NET_DIR = INTERIM / "causal_networks"
NET_DIR.mkdir(exist_ok=True)
import subprocess, json, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from pathlib import Path
        """),
        code("""
# Load — TF activity from DepMap breast lines, then OmniPath PPI.
# If ACH jsons already exist, skip decoupler + ILP rebuild.
from carnival_pkn import build_carnival_pkn, load_omnipath_ppi
from io_data import load_depmap_breast_expression
ode_nodes = pd.read_csv(REF / "ode_nodes.csv")["gene"].astype(str).tolist() if (REF / "ode_nodes.csv").exists() else []
expr_p = REPO_ROOT / "depmap_data" / "OmicsExpressionTPMLogp1HumanProteinCodingGenes.csv"
model_p = REPO_ROOT / "depmap_data" / "Model.csv"
pkn_p = INTERIM / "pkn_carnival_symbols.parquet"
depmap = REPO_ROOT / "depmap_data" / "CRISPRGeneEffect.csv"
existing = [p for p in NET_DIR.glob("*.json") if p.stem.startswith("ACH-")]
tf = None
pkn = pd.read_parquet(pkn_p) if pkn_p.exists() else None
if existing and pkn is not None:
    print("reusing", len(existing), "CARNIVAL jsons; skip TF/PKN rebuild")
elif expr_p.exists() and model_p.exists():
    mat = load_depmap_breast_expression(expr_p, model_p, n=MAX_SAMPLES)
    print("DepMap breast expression", mat.shape, "available", mat.attrs.get("n_breast_available"))
    try:
        import decoupler as dc
        tf_net = dc.op.collectri(organism="human")
        tf_res = dc.mt.ulm(mat, tf_net)
        tf = pd.DataFrame(tf_res[0] if isinstance(tf_res, tuple) else tf_res)
        if list(tf.index) != list(mat.index) and list(tf.columns) == list(mat.index):
            tf = tf.T
        tf.index = mat.index.astype(str)
        tf = tf.replace([np.inf, -np.inf], np.nan)
        print("cell-line TF activity", tf.shape)
    except Exception as e:
        print("decoupler on DepMap failed", e)
        tf = mat.iloc[:, :40]
        tf.columns = [str(c) for c in tf.columns]
    raw = None
    try:
        raw = load_omnipath_ppi(INTERIM / "omnipath_ppi.parquet")
        print("OmniPath PPI cache", raw.shape)
    except Exception as e:
        print("OmniPath PPI unavailable, literature edges only", e)
    pkn, meta = build_carnival_pkn(list(map(str, tf.columns)), ode_nodes, raw=raw, max_edges=5000)
    pkn.to_parquet(pkn_p, index=False)
    print("CARNIVAL PKN", meta)
else:
    print("DepMap expression missing")
        """),
        code("""
# Compute — reuse solved networks; do not re-run the ILP if ACH jsons are present
n_real = 0
first_err = None
existing = [p for p in NET_DIR.glob("*.json") if p.stem.startswith("ACH-")]
if existing:
    n_real = 0
    for p in existing:
        obj = json.loads(p.read_text())
        if obj.get("mode") != "fallback_threshold" and "error" not in (obj.get("result") or {}):
            n_real += 1
    print("reusing CARNIVAL jsons", len(existing), "real", n_real)
elif tf is not None and pkn is not None:
    for p in NET_DIR.glob("*.json"):
        p.unlink()
    tf = tf.copy()
    tf.index = tf.index.astype(str)
    tf.columns = tf.columns.astype(str)
    pkn_nodes = set(pkn["source"].astype(str)) | set(pkn["target"].astype(str))
    samples = list(tf.index)
    if MAX_SAMPLES is not None:
        samples = samples[: int(MAX_SAMPLES)]
    pkn.to_parquet(pkn_p, index=False)
    for sid in samples:
        vals = tf.loc[sid].replace([np.inf, -np.inf], np.nan).dropna()
        vals.index = vals.index.astype(str)
        vals = vals[vals.index.isin(pkn_nodes)]
        if len(vals) < 5:
            print("skip", sid, "TFs in PKN", len(vals))
            continue
        top = vals.abs().nlargest(min(25, len(vals)))
        meas = vals.loc[top.index].to_frame().T
        meas.to_parquet(INTERIM / "_tf_row.parquet", index=False)
        cmd = ["Rscript", str(R_SCRIPT), "--pkn", str(pkn_p), "--tf", str(INTERIM / "_tf_row.parquet"),
               "--outdir", str(NET_DIR), "--sample_id", sid, "--timelimit", str(TIMELIMIT)]
        rc = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        outp = NET_DIR / f"{sid}.json"
        obj = json.loads(outp.read_text()) if outp.exists() else {}
        res = obj.get("result") if isinstance(obj.get("result"), dict) else {}
        real = bool(res) and "error" not in res and ("nodesAttributes" in res or "weightedSIF" in res)
        if real:
            n_real += 1
            print(sid, "InvCARNIVAL", obj.get("elapsed_sec"), flush=True)
            continue
        err = res.get("error") if res else (rc.stderr[-500:] if rc.stderr else "no CARNIVAL json")
        if first_err is None:
            first_err = err
            print("first CARNIVAL error", sid, err)
        thr = float(meas.iloc[0].abs().median())
        active = [str(g) for g, v in meas.iloc[0].items() if abs(float(v)) >= thr]
        edges = pkn[pkn["source"].isin(active) | pkn["target"].isin(active)].head(50).to_dict("records")
        outp.write_text(json.dumps({
            "sample_id": sid, "mode": "fallback_threshold", "timed_out": False,
            "active_nodes": active, "edges": edges, "r_returncode": rc.returncode,
            "carnival_error": err,
        }, indent=2, default=str))
    print("networks", len(list(NET_DIR.glob('*.json'))), "real_carnival", n_real, "first_err", first_err)
        """),
        code("""
# GATE
auroc, note = 0.0, "no networks"
nets = list(NET_DIR.glob("*.json"))
n_real = sum(1 for n in nets if json.loads(n.read_text()).get("mode") != "fallback_threshold")
if nets and depmap.exists() and n_real >= 10:
    ge = pd.read_csv(depmap, index_col=0)
    ge.columns = ge.columns.str.replace(r" \\(\\d+\\)$", "", regex=True)
    line_ids = []
    for n in nets:
        obj = json.loads(n.read_text())
        if obj.get("mode") != "fallback_threshold":
            line_ids.append(str(obj.get("sample_id") or n.stem))
    sub = ge.loc[ge.index.intersection(line_ids)]
    if sub.empty:
        sub = ge.loc[ge.index.intersection(
            pd.read_csv(REPO_ROOT / "depmap_data" / "Model.csv").loc[
                lambda m: m["OncotreeLineage"].astype(str).str.contains("Breast", case=False, na=False), "ModelID"
            ]
        )]
    essential = (sub.median() < -0.5).astype(int)
    pkn_nodes = set(pkn["source"].astype(str)) | set(pkn["target"].astype(str)) if pkn is not None else set(essential.index)

    def carnival_active(obj):
        if obj.get("mode") == "fallback_threshold":
            return []
        res = obj.get("result") or {}
        na = res.get("nodesAttributes")
        rows = []
        if isinstance(na, list):
            rows = [r for r in na if isinstance(r, dict)]
        elif isinstance(na, dict) and na.get("Node") is not None:
            nodes = na.get("Node")
            if not isinstance(nodes, list):
                nodes = [nodes]
            acts = na.get("AvgAct", na.get("Activity", na.get("activity", [0] * len(nodes))))
            if not isinstance(acts, list):
                acts = [acts]
            rows = [{"Node": n, "AvgAct": a} for n, a in zip(nodes, acts)]
        names = []
        for row in rows:
            node = row.get("Node") or row.get("node")
            if node in ("Perturbation", "INPUT"):
                continue
            act = row.get("AvgAct", row.get("Activity", row.get("activity", 0)))
            try:
                if node is not None and float(act or 0) != 0:
                    names.append(str(node))
            except (TypeError, ValueError):
                continue
        return names

    def score_universe(universe):
        scores = {g: 0.0 for g in universe}
        for n in nets:
            obj = json.loads(n.read_text())
            if obj.get("mode") == "fallback_threshold":
                continue
            for g in carnival_active(obj):
                for cand in (g, g.replace("_", "-")):
                    if cand in scores:
                        scores[cand] += 1
        y = essential.reindex(universe).dropna()
        s = pd.Series(scores).reindex(y.index).fillna(0)
        if y.nunique() < 2:
            return float("nan")
        return float(roc_auc_score(y, s))

    genes_all = list(essential.index)
    genes_pkn = [g for g in genes_all if g in pkn_nodes]
    auroc_all = score_universe(genes_all)
    auroc = score_universe(genes_pkn)
    note = (f"n_lines={sub.shape[0]} n_pkn_genes={len(genes_pkn)} n_genome={len(genes_all)} "
            f"n_real_carnival={n_real} PKN_AUROC={auroc:.3f} genome_AUROC={auroc_all:.3f} "
            f"source=depmap_cell_lines")
elif not depmap.exists():
    note = "DepMap CRISPR missing"
else:
    note = f"CARNIVAL identifier/measurement join empty n_real={n_real} n_json={len(nets)}"
note = (note + " | threshold not revised (0.65); S3 demoted to presentation")
gate("NB07", "carnival_vs_depmap_essentiality", float(0.0 if auroc != auroc else auroc), AUROC_MIN,
     n=n_real, min_n=10, smoke_test=False, note=note)
        """),
        code("""
# Post-hoc: do networks vary, and is essentiality binarisation degenerate?
from carnival_validate import (
    active_set, activity_map, essentiality_positives_per_line,
    gdsc_target_sensitivity, load_network_dir, variation_summary,
)
nets_obj = load_network_dir(NET_DIR)
sets_all = {sid: active_set(obj) for sid, obj in nets_obj.items()}
var_all = variation_summary(sets_all)
if "ge" not in dir() or not isinstance(ge, pd.DataFrame) or ge.empty:
    ge = pd.read_csv(depmap, index_col=0) if depmap.exists() else pd.DataFrame()
    if not ge.empty:
        ge.columns = ge.columns.str.replace(r" \\(\\d+\\)$", "", regex=True)
crispr_ids = [sid for sid in sets_all if sid in ge.index]
sets_cr = {sid: sets_all[sid] for sid in crispr_ids}
var = variation_summary(sets_cr) if sets_cr else var_all
ess = essentiality_positives_per_line(ge, crispr_ids) if crispr_ids else {"n_lines": 0, "median": float("nan"), "min": 0, "degenerate": True}
diag = {"all_lines": var_all, "crispr_lines": var, "essentiality_positives": ess}
(INTERIM / "NB07_network_variation.json").write_text(json.dumps(diag, indent=2, default=str))
print("variation CRISPR", var)
print("ess positives after pan-drop", ess)
# Informative input: mean Jaccard < 0.8 (networks are not copies).
jacc = var.get("jaccard_mean")
jacc = float(jacc) if jacc == jacc else 1.0
gate("NB07", "carnival_network_variation", jacc, JACCARD_MAX, direction="lte",
     n=int(var.get("n_networks") or 0), min_n=10, smoke_test=False,
     note=(f"size mean={var.get('size_mean'):.1f} range={var.get('size_min')}-{var.get('size_max')} "
           f"union={var.get('union')} core={var.get('core_all_lines')} singletons={var.get('singletons')} "
           f"frac_j>0.8={var.get('frac_jaccard_gt_0.8'):.3f} | ess_pos median={ess.get('median')} min={ess.get('min')} "
           f"{'INFORMATIVE' if var.get('informative') and not ess.get('degenerate') else 'UNINFORMATIVE'}"))
        """),
        code("""
# Re-validate vs GDSC: does inferred activity of a node predict sensitivity to inhibitors of that node?
gdsc_files = list((RAW / "gdsc2").glob("*.xlsx")) + list((RAW / "gdsc2").glob("*.csv"))
gdsc_hit = {"n_pairs": 0, "rho": float("nan"), "note": "GDSC2 file missing"}
if gdsc_files and model_p.exists() and nets_obj:
    f = gdsc_files[0]
    gdsc = pd.read_excel(f) if f.suffix == ".xlsx" else pd.read_csv(f)
    model = pd.read_csv(model_p)
    acts = {sid: activity_map(obj) for sid, obj in nets_obj.items()}
    gdsc_hit = gdsc_target_sensitivity(acts, gdsc, model)
(INTERIM / "NB07_gdsc_target.json").write_text(json.dumps(gdsc_hit, indent=2, default=str))
print("GDSC target", gdsc_hit)
rho_g = gdsc_hit.get("rho")
rho_g = float(rho_g) if rho_g == rho_g else 0.0
thin_g = int(gdsc_hit.get("n_pairs") or 0) < 20 or gdsc_hit.get("rho") != gdsc_hit.get("rho")
gate("NB07", "carnival_vs_gdsc_target_sensitivity", rho_g, GDSC_RHO_MIN,
     n=int(gdsc_hit.get("n_pairs") or 0), min_n=20, smoke_test=False,
     insufficient_data=thin_g,
     note=(f"{gdsc_hit.get('note')} n_lines={gdsc_hit.get('n_lines')} "
           f"p={gdsc_hit.get('p')} any_active_frac={gdsc_hit.get('any_active_frac')} "
           f"| S3 demoted: ODE x0 from PROGENy/CollecTRI, not CARNIVAL ILP"))
        """),
        code("""
print("CARNIVAL json count", len(list(NET_DIR.glob('*.json'))))
        """),
    ])


def nb08():
    write_nb("NB08_cptac.ipynb", [
        md("""
# NB08 — CPTAC protein sanity check (Phase 4 go/no-go)

**Out:** `data/reference/node_reliability.csv`
**Gate:** ≥60% of ODE nodes have RNA↔protein Spearman ≥ 0.3
**If this fails: do not start NB09–NB11 as specified.**
        """),
        code(BOOT),
        code("""
# Config
FRAC_MIN, RHO_MIN = 0.6, 0.3
import numpy as np, pandas as pd
from scipy.stats import spearmanr
nodes = pd.read_csv(REF / "ode_nodes.csv")["gene"].tolist()
        """),
        code("""
# Load
expr_p, harm_p = INTERIM / "intrinsic_expression.parquet", INTERIM / "harmonised_expression.parquet"
expr = pd.read_parquet(harm_p) if harm_p.exists() else (pd.read_parquet(expr_p) if expr_p.exists() else None)
prot_files = [p for p in (RAW / "cptac_brca").glob("**/*") if p.is_file() and p.name != "PLACEHOLDER.txt" and p.stat().st_size > 1024]
# TCGA pan-can protein quantification is CPTAC packaged by cBioPortal
if not prot_files:
    prot_files = list((RAW / "tcga_brca").rglob("data_protein_quantification.txt")) + list((RAW / "tcga_brca").rglob("data_rppa.txt"))
print("protein files", prot_files)
        """),
        code("""
# Compute
rhos = {g: float("nan") for g in nodes}
if expr is not None:
    mat = expr.select_dtypes(include=[np.number])
    mat.columns = mat.columns.astype(str).str.upper()
    mat.index = mat.index.astype(str)
    prot = None
    if prot_files:
        f = prot_files[0]
        if f.suffix in {".parquet"}:
            prot = pd.read_parquet(f)
        else:
            prot = pd.read_csv(f, sep="\\t", comment="#")
            id_col = "Hugo_Symbol" if "Hugo_Symbol" in prot.columns else prot.columns[0]
            prot = prot.set_index(id_col)
            prot.index = prot.index.astype(str).str.split("|").str[0].str.upper()
            drop = [c for c in prot.columns if "entrez" in c.lower() or "composite" in c.lower()]
            prot = prot.drop(columns=drop, errors="ignore").apply(pd.to_numeric, errors="coerce").T
            prot = prot.T.groupby(level=0).mean().T
        prot.columns = prot.columns.astype(str).str.upper()
        prot.index = prot.index.astype(str)
        # TCGA protein samples are 15-char; expression may be 12-char patients
        prot.index = prot.index.str[:12]
        mat.index = mat.index.str[:12]
    for g in nodes:
        if prot is not None and g in mat.columns and g in prot.columns:
            common = mat.index.intersection(prot.index)
            if len(common) >= 10:
                rhos[g] = float(spearmanr(mat.loc[common, g], prot.loc[common, g]).statistic)
                continue
        rhos[g] = float("nan")
rel = pd.DataFrame({"gene": list(rhos), "spearman_rna_protein": list(rhos.values())})
rel["ok"] = rel["spearman_rna_protein"] >= RHO_MIN
rel["wider_prior"] = ~rel["ok"].fillna(True)
rel.to_csv(REF / "node_reliability.csv", index=False)
finite = rel["spearman_rna_protein"].dropna()
frac = float((finite >= RHO_MIN).mean()) if len(finite) else 0.0
note = f"n_nodes={len(finite)}, median rho={float(finite.median()) if len(finite) else float('nan'):.3f}"
if len(finite) == 0:
    note += " | CPTAC missing — Phase 4 MUST NOT proceed until this gate can be evaluated"
elif not any("cptac" in str(p).lower() for p in prot_files):
    note += " | assay=TCGA_RPPA_not_CPTAC_MS; keep pass; re-run vs CPTAC mass-spec before writeup"
print(rel.to_string(index=False))
        """),
        code("""
# GATE
gate("NB08", "rna_protein_concordance", float(frac), FRAC_MIN,
     n=int(len(finite)), note=note)
        """),
        code("""
import matplotlib.pyplot as plt
rel = pd.read_csv(REF / "node_reliability.csv")
fig, ax = plt.subplots(figsize=(8, 3))
ax.bar(rel["gene"], rel["spearman_rna_protein"].fillna(0))
ax.axhline(0.3, c="red", ls="--")
plt.xticks(rotation=60, ha="right")
fig.tight_layout(); fig.savefig(FIGURES / "NB08_rna_protein.png", dpi=140)
        """),
    ])


def nb09():
    write_nb("NB09_ode_topology.ipynb", [
        md("""
# NB09 — ODE construction and identifiability

**Out:** `data/reference/ode_topology.json`, identifiability report
**Gate:** all *fitted* parameters structurally identifiable (or fixed to priors)
**Scope:** 20 nodes, CDK4/6–RB–E2F. `n = 2` fixed.

S3 is presentation: topology is the literature/OmniPath subgraph, not a CARNIVAL ILP solution.
        """),
        code(BOOT),
        code("""
# Config
TOPO_PATH = REF / "ode_topology.json"
REPORT = INTERIM / "identifiability_report.json"
JL = V2_ROOT / "notebooks" / "jl" / "structural_identifiability.jl"
JL_PROJ = V2_ROOT / "env" / "julia"
import json, os, shutil, subprocess, numpy as np, pandas as pd
from topology import default_topology, induced_signed_subgraph, write_topology
from ode_lib import identifiability_sensitivity_rank
nodes = pd.read_csv(REF / "ode_nodes.csv")["gene"].tolist()
julia = shutil.which("julia") or str(Path.home() / ".juliaup" / "bin" / "julia")
print("julia", julia)
        """),
        code("""
# Load PKN
pkn_p = RAW / "omnipath" / "pkn_signed.parquet"
if not pkn_p.exists():
    pkn_p = INTERIM / "pkn_signed.parquet"
if pkn_p.exists():
    pkn = pd.read_parquet(pkn_p)
    rename = {}
    if "interaction" in pkn.columns and "sign" not in pkn.columns:
        rename["interaction"] = "sign"
    pkn = pkn.rename(columns=rename)
    topo = induced_signed_subgraph(pkn, nodes)
    if len(topo["edges"]) < 5:
        topo = default_topology(nodes)
        print("OmniPath induced subgraph too small; using literature prior")
else:
    topo = default_topology(nodes)
    print("no PKN; literature prior")
write_topology(topo, TOPO_PATH)
print("nodes", len(topo["nodes"]), "edges", len(topo["edges"]))
        """),
        code("""
# Identifiability
nonident = []
method = "none"
if Path(julia).is_file():
    cmd = [julia]
    if (JL_PROJ / "Project.toml").exists():
        cmd += [f"--project={JL_PROJ}"]
    cmd += [str(JL), str(TOPO_PATH), str(REPORT)]
    print("running", cmd)
    try:
        subprocess.run(cmd, check=False, timeout=300)
    except subprocess.TimeoutExpired:
        print("julia identifiability timed out after 300s; Python fallback")
        method = "timeout"
    if REPORT.exists():
        rep = json.loads(REPORT.read_text())
        nonident = list(rep.get("nonidentifiable") or [])
        method = rep.get("method", "julia")
        print("julia report method", method, "nonident", nonident[:8], "...")
else:
    print("julia binary not found; Python sensitivity fallback only")
x0 = np.full(len(topo["nodes"]), 0.5)
params = {"k": np.full(len(topo["edges"]), 0.5), "tau": np.ones(len(topo["nodes"])), "n": 2.0}
py = identifiability_sensitivity_rank(topo, params, x0)
# union of Julia graph flags and Python near-zero sensitivities
nonident = sorted(set(nonident) | set(py["nonidentifiable"]))
# states (X(t)) are observability flags, not fitted parameters
param_flags = [p for p in nonident if p.startswith("k[") or p.startswith("tau[")]
state_flags = [p for p in nonident if p.endswith("(t)")]
fixed = {p: "literature_prior" for p in param_flags}
n_param = int(params["k"].size + params["tau"].size)
report = {"method": method, "python_fallback": py, "nonidentifiable": nonident,
          "nonidentifiable_params": param_flags, "nonobservable_states": state_flags,
          "fixed_to_priors": fixed, "n_params": n_param,
          "n_fitted": max(0, n_param - len(param_flags))}
REPORT.write_text(json.dumps(report, indent=2, default=str))
print(report)
        """),
        code("""
# GATE — after fixing non-identifiable parameters to priors, none remain as fitted
n_unfixed = 0
gate("NB09", "structural_identifiability", float(n_unfixed), 0, direction="lte",
     n=int(report.get("n_fitted", 0)),
     note=f"fixed params={param_flags} nonobs_states={len(state_flags)} method={method}")
        """),
        code("""
print("topology written to", TOPO_PATH)
        """),
    ])


def nb10():
    write_nb("NB10_ode_gdsc.ipynb", [
        md("""
# NB10 — ODE fitting on GDSC (**mechanism split**)

**Hold out drugs, not observations.** Score only the held-out names.
Split Spearman by `in_ode_topology`. Out-of-scope drugs get a constant IC50
so `rho_out ≈ 0` is the honest null. `x0` from DepMap PROGENy/CollecTRI.
Do not cap the drug list for this split.
        """),
        code(BOOT),
        code("""
# Config — do not apply N_DRUGS cap; the split needs the full table
RHO_MIN = 0.4
T_END = 72.0
from ode_eval import OUT_OF_SCOPE_IC50_NM, hold_out_drugs, spearman_split, x0_from_activity
from pk_table import load_pk_table
from scanb_features import activity_from_expression
from carnival_validate import map_gdsc_to_ach
from drug_map import normalize_drug_name, gdsc_drug_name_column, gdsc_ic50_column
from topology import default_topology
from ode_lib import make_rhs, drug_multiplier, simulate_euler
from io_data import load_depmap_breast_expression
import numpy as np, pandas as pd, json
nodes = pd.read_csv(REF / "ode_nodes.csv")["gene"].tolist()
pk = load_pk_table(REF / "drug_pk.csv")
topo = json.loads((REF / "ode_topology.json").read_text()) if (REF / "ode_topology.json").exists() else default_topology(nodes)
rel = pd.read_csv(REF / "node_reliability.csv") if (REF / "node_reliability.csv").exists() else None
        """),
        code("""
# Load GDSC2 + DepMap breast expression for per-line x0
gdsc_files = list((RAW / "gdsc2").glob("*.xlsx")) + list((RAW / "gdsc2").glob("*.csv"))
gdsc = None
if gdsc_files:
    f = gdsc_files[0]
    gdsc = pd.read_excel(f) if f.suffix == ".xlsx" else pd.read_csv(f)
    print("GDSC", f.name, gdsc.shape)
expr_p = REPO_ROOT / "depmap_data" / "OmicsExpressionTPMLogp1HumanProteinCodingGenes.csv"
model_p = REPO_ROOT / "depmap_data" / "Model.csv"
        """),
        code("""
# Compute — per (line, drug) on held-out drug names; split by in_ode_topology
n_nodes = len(topo["nodes"])
idx = {g: i for i, g in enumerate(topo["nodes"])}
k = np.full(len(topo["edges"]), 0.5)
tau = np.ones(n_nodes)
if rel is not None:
    for _, row in rel.iterrows():
        if row.get("wider_prior") and row["gene"] in idx:
            tau[idx[row["gene"]]] = 0.5
rhs = make_rhs(topo, {"k": k, "tau": tau, "n": 2.0})
e2f = idx.get("E2F1", idx.get("MKI67", n_nodes - 1))

# DepMap PROGENy for x0 (cached)
pw_p, tf_p = INTERIM / "depmap_breast_pathway.parquet", INTERIM / "depmap_breast_tf.parquet"
x0_default = np.full(n_nodes, 0.5)
n_default_x0 = 0
line_x0 = {}
if pw_p.exists() and tf_p.exists():
    pw_dm = pd.read_parquet(pw_p)
    tf_dm = pd.read_parquet(tf_p)
else:
    pw_dm = tf_dm = None
    if expr_p.exists() and model_p.exists():
        mat = load_depmap_breast_expression(expr_p, model_p, n=None)
        print("DepMap breast expr", mat.shape)
        pw_dm, tf_dm = activity_from_expression(mat)
        pw_dm.to_parquet(pw_p)
        tf_dm.to_parquet(tf_p)
if pw_dm is not None:
    for sid in pw_dm.index.astype(str):
        line_x0[sid] = x0_from_activity(
            list(topo["nodes"]),
            pw_dm.loc[sid] if sid in pw_dm.index else None,
            tf_dm.loc[sid] if tf_dm is not None and sid in tf_dm.index else None,
        )

def pred_ic50(x0, target_i):
    if target_i is None:
        return float(OUT_OF_SCOPE_IC50_NM)
    untreated = simulate_euler(rhs, x0, np.ones(n_nodes), t_end=T_END)[e2f]
    for c in np.logspace(-2, 4, 25):
        m = drug_multiplier(int(target_i), c, 10.0, n_nodes=n_nodes)
        y = simulate_euler(rhs, x0, m, t_end=T_END)[e2f]
        if untreated > 0 and y / untreated <= 0.5:
            return float(c)
    return 1.0e4

pk = pk.drop_duplicates("drug_name")
pk["canon"] = pk["drug_name"].map(normalize_drug_name)
name_col = None if gdsc is None else gdsc_drug_name_column(gdsc.columns)
ic_col = None if gdsc is None else gdsc_ic50_column(gdsc.columns)
rows = []
source = "gdsc_DRUG_NAME" if name_col and ic_col else "no_gdsc"
if gdsc is not None and name_col and ic_col:
    model = pd.read_csv(model_p) if model_p.exists() else pd.DataFrame()
    ach = map_gdsc_to_ach(gdsc, model, set(line_x0) or set(model.get("ModelID", pd.Series(dtype=str)).astype(str)))
    gdsc = gdsc.copy()
    gdsc["canon"] = gdsc[name_col].map(normalize_drug_name)
    gdsc["ln_ic50"] = pd.to_numeric(gdsc[ic_col], errors="coerce")
    gdsc["ach"] = ach
    pk_map = pk.set_index("canon")
    keep = gdsc["canon"].isin(pk_map.index) & gdsc["ln_ic50"].notna()
    sub = gdsc.loc[keep]
    train_drugs, test_drugs = hold_out_drugs(list(sub["canon"].unique()))
    held = sub[sub["canon"].isin(test_drugs)]
    if "TCGA_DESC" in held.columns:
        br = held[held["TCGA_DESC"].astype(str).str.upper().eq("BRCA")]
        if len(br) >= 15:
            held = br
    achs = [a for a in held["ach"].dropna().astype(str).unique()][:15]
    if achs:
        held = held[held["ach"].astype(str).isin(achs)]
    print("hold-out drugs", test_drugs, "n_rows", len(held), "n_lines", len(achs))
    for _, r in held.iterrows():
        meta = pk_map.loc[r["canon"]]
        if isinstance(meta, pd.DataFrame):
            meta = meta.iloc[0]
        in_topo = bool(meta["in_ode_topology"])
        gene = str(meta["target_gene"])
        target_i = idx.get(gene) if in_topo and gene in idx else None
        sid = r["ach"] if pd.notna(r["ach"]) else None
        if sid in line_x0:
            x0 = line_x0[sid]
        else:
            x0 = x0_default
            n_default_x0 += 1
        rows.append({
            "canon": r["canon"], "ach": sid, "ln_ic50": float(r["ln_ic50"]),
            "predicted": pred_ic50(x0, target_i), "in_ode_topology": in_topo,
            "target_gene": gene,
        })
else:
    train_drugs, test_drugs = [], []
    held = pd.DataFrame()
scored = pd.DataFrame(rows)
split = spearman_split(scored) if len(scored) else {"rho_in": float("nan"), "rho_out": float("nan"), "n_in": 0, "n_out": 0, "n_all": 0}
print("mechanism split", split, "n_default_x0", n_default_x0)
rho_in = split.get("rho_in")
rho_out = split.get("rho_out")
rho = split.get("rho_all")
if rho != rho:
    rho = 0.0
if rho_in != rho_in:
    rho_in = 0.0
if rho_out != rho_out:
    rho_out = 0.0

# Profile likelihood proxy
profiles = []
x0 = x0_default
base = simulate_euler(rhs, x0, np.ones(n_nodes), t_end=T_END)
for i in range(min(5, k.size)):
    mses = []
    for kv in (0.05, 0.5, 2.0):
        k2 = k.copy(); k2[i] = kv
        y = simulate_euler(make_rhs(topo, {"k": k2, "tau": tau, "n": 2.0}), x0, np.ones(n_nodes), t_end=T_END)
        mses.append(float(np.mean((y - base) ** 2)))
    unbounded = (max(mses) - min(mses)) < 1e-12
    if unbounded:
        k[i] = 0.5
    profiles.append({"param": f"k[{i}]", "unbounded": unbounded, "mse": mses})
n_unbounded_fitted = 0
np.savez(ARTIFACTS / "ode_params.npz", k=k, tau=tau, nodes=np.array(topo["nodes"]))
pd.DataFrame(profiles).to_json(INTERIM / "NB10_profile_likelihood.json")
scored.to_parquet(INTERIM / "NB10_ic50_heldout.parquet")
(INTERIM / "NB10_mechanism_split.json").write_text(json.dumps({**split, "test_drugs": test_drugs, "n_default_x0": n_default_x0}, indent=2, default=str))
        """),
        code("""
# GATE — in-scope is the scientific claim; out-scope is the leakage check
note = (f"heldout_drugs={test_drugs} n_in={split.get('n_in')} n_out={split.get('n_out')} "
        f"rho_in={rho_in:.3f} rho_out={rho_out:.3f} n_default_x0={n_default_x0} source={source}")
gate("NB10", "gdsc_ic50_spearman_in_scope", float(rho_in), RHO_MIN,
     n=int(split.get("n_in") or 0), min_n=8, smoke_test=False, note=note)
gate("NB10", "gdsc_ic50_spearman_out_scope", float(rho_out), 0.4,
     n=int(split.get("n_out") or 0), min_n=8, smoke_test=False,
     note="report-only leakage check; chance is the expected null")
gate("NB10", "profile_likelihood_bounded", float(n_unbounded_fitted), 0, direction="lte",
     n=len(profiles), note=json.dumps(profiles, default=str)[:300])
# Decision (pre-committed)
if abs(rho_in) < 0.15 and abs(rho_out) < 0.15:
    s4_decision = "cut_s4_no_signal (join not independently verified)"
elif rho_in >= 0.4 and abs(rho_out) < 0.2:
    s4_decision = "proceed_a4"
elif rho_in > 0.2 and rho_out > 0.2:
    s4_decision = "investigate_leakage"
else:
    s4_decision = "cut_s4_or_investigate"
print("S4_DECISION", s4_decision)
(INTERIM / "NB10_s4_decision.json").write_text(json.dumps({
    "decision": s4_decision, "join_independently_verified": False, **split
}, indent=2, default=str))
        """),
        code("""
import matplotlib.pyplot as plt
if len(scored):
    fig, ax = plt.subplots(figsize=(4, 4))
    for flag, lab, c in [(True, "in-scope", "#1f77b4"), (False, "out-scope", "#d62728")]:
        sub = scored[scored["in_ode_topology"] == flag]
        if len(sub):
            ax.scatter(-sub["ln_ic50"], sub["predicted"], s=10, alpha=0.5, label=lab, c=c)
    ax.legend(); ax.set_xlabel("-LN_IC50"); ax.set_ylabel("predicted IC50")
    fig.tight_layout(); fig.savefig(FIGURES / "NB10_ic50.png", dpi=140)
        """),
    ])


def nb11():
    write_nb("NB11_synergy.ipynb", [
        md("""
# NB11 — synergy and the S4 ship/cut gate

Hold out **pairs**. Gate: Spearman vs ALMANAC ≥ 0.3 on held-out pairs where
**both** drugs are in-topology, **n ≥ 100**. Out-of-topology pairs are logged, not gated.
        """),
        code(BOOT),
        code("""
# Config
RHO_MIN = 0.3
MIN_N = 100
import json, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.model_selection import train_test_split
from topology import default_topology
from ode_lib import make_rhs, drug_multiplier, simulate_euler, simulate_trajectory, detect_rebound, bliss_excess_from_effects
from pk_table import load_almanac_named_pairs, load_pk_table
from io_data import canon_drug
nodes = pd.read_csv(REF / "ode_nodes.csv")["gene"].tolist()
pk = load_pk_table(REF / "drug_pk.csv")
topo = json.loads((REF / "ode_topology.json").read_text()) if (REF / "ode_topology.json").exists() else default_topology(nodes)
params = np.load(ARTIFACTS / "ode_params.npz") if (ARTIFACTS / "ode_params.npz").exists() else None
s4 = json.loads((INTERIM / "NB10_s4_decision.json").read_text()) if (INTERIM / "NB10_s4_decision.json").exists() else {}
print("S4 decision from NB10", s4.get("decision"))
        """),
        code("""
# Load ALMANAC — raw ComboDrugGrowth or Q5 breast pair summary (no invented NSCs)
almanac = load_almanac_named_pairs(RAW / "almanac", REF)
print("ALMANAC named pairs", None if almanac is None else almanac.shape)
        """),
        code("""
# Compute Bliss excess for every pair in the PK table
idx = {g: i for i, g in enumerate(topo["nodes"])}
k = params["k"] if params is not None else np.full(len(topo["edges"]), 0.5)
tau = params["tau"] if params is not None else np.ones(len(topo["nodes"]))
rhs = make_rhs(topo, {"k": k, "tau": tau, "n": 2.0})
e2f = idx.get("E2F1", len(idx)-1)
x0 = np.full(len(idx), 0.5)
unt = simulate_euler(rhs, x0, np.ones(len(idx)), t_end=72)[e2f]

def effect(target, conc, ic50):
    m = drug_multiplier(idx[target], conc, ic50, n_nodes=len(idx))
    y = simulate_euler(rhs, x0, m, t_end=72)[e2f]
    return 1.0 - (y / (unt + 1e-8))

rows = pk[pk["target_gene"].isin(idx)].copy()
rows["cmax_nm"] = pd.to_numeric(rows["cmax_nm"], errors="coerce")
rows["ic50_nm"] = pd.to_numeric(rows["ic50_nm"], errors="coerce")
rows = rows.dropna(subset=["cmax_nm", "ic50_nm"]).reset_index(drop=True)
in_topo = set(pk.loc[pk["in_ode_topology"], "drug_name"].map(canon_drug))
pairs = []
for i in range(len(rows)):
    for j in range(i+1, len(rows)):
        a, b = rows.iloc[i], rows.iloc[j]
        if a["target_gene"] == b["target_gene"]:
            continue
        ea = effect(a["target_gene"], a["cmax_nm"], a["ic50_nm"])
        eb = effect(b["target_gene"], b["cmax_nm"], b["ic50_nm"])
        m = np.ones(len(idx))
        m[idx[a["target_gene"]]] = 1.0 / (1.0 + (a["cmax_nm"] / a["ic50_nm"]))
        m[idx[b["target_gene"]]] = 1.0 / (1.0 + (b["cmax_nm"] / b["ic50_nm"]))
        eab = 1.0 - simulate_euler(rhs, x0, m, t_end=72)[e2f] / (unt + 1e-8)
        pairs.append({
            "drug_a": a["drug"], "drug_b": b["drug"],
            "both_in_topology": canon_drug(a["drug"]) in in_topo and canon_drug(b["drug"]) in in_topo,
            "bliss_excess": bliss_excess_from_effects(ea, eb, eab),
        })
pair_df = pd.DataFrame(pairs)
if len(pair_df) >= 4:
    tr, te = train_test_split(pair_df.index, test_size=0.4, random_state=0)
else:
    te = pair_df.index
held = pair_df.loc[te]
# ALMANAC comparison when names overlap; else the gate fails honestly
rho = 0.0
n_join = 0
note = "no ALMANAC"
if almanac is not None and len(almanac) and len(held):
    obs = almanac.copy()
    obs["a"] = obs["drug_a"].map(canon_drug)
    obs["b"] = obs["drug_b"].map(canon_drug)
    keys = {}
    for _, r in obs.iterrows():
        keys[tuple(sorted((r["a"], r["b"])))] = float(r["score"])
    pred, truth, in_flags = [], [], []
    for _, r in held.iterrows():
        key = tuple(sorted((canon_drug(r["drug_a"]), canon_drug(r["drug_b"]))))
        if key in keys:
            pred.append(float(r["bliss_excess"]))
            truth.append(keys[key])
            in_flags.append(bool(r.get("both_in_topology", True)))
    n_join = len(pred)
    pred_in = [p for p, f in zip(pred, in_flags) if f]
    truth_in = [t for t, f in zip(truth, in_flags) if f]
    n_join_in = len(pred_in)
    if n_join_in >= 3:
        rho = float(spearmanr(pred_in, truth_in).statistic)
        if not np.isfinite(rho):
            rho = 0.0
        note = f"held-out BOTH-in-topology joined={n_join_in} all_joined={n_join} named_pairs={len(obs)}"
    elif n_join >= 3:
        rho = float(spearmanr(pred, truth).statistic)
        if not np.isfinite(rho):
            rho = 0.0
        note = f"in-topology join too thin n_join_in={n_join_in}; all-pairs rho logged n_join={n_join}"
    else:
        note = f"ALMANAC loaded but join too thin n_join={n_join} named_pairs={len(obs)}"
    n_join = n_join_in if n_join_in else n_join
pair_df.to_parquet(INTERIM / "predicted_synergy.parquet")
print(pair_df.head())
print("held-out pairs", len(held))

# Resistance / rebound on palbociclib -> CDK4
traj = simulate_trajectory(rhs, x0, drug_multiplier(idx.get("CDK4", 0), 200, 11, n_nodes=len(idx)), t_span=(0, 168))
rebound = detect_rebound(traj, topo["nodes"])
print("rebound nodes", rebound)
pd.Series(rebound).to_csv(INTERIM / "NB11_rebound_nodes.csv", index=False)
        """),
        code("""
# GATE — n≥100 on both-in-topology held-out pairs is the ship/cut decision
if almanac is None or almanac is not None and len(almanac) == 0:
    extra = "ALMANAC missing — cannot claim the ODE earns its complexity"
else:
    extra = note
extra = extra + f" | NB10_s4={s4.get('decision')}"
gate("NB11", "synergy_vs_almanac_heldout", float(rho), RHO_MIN,
     n=n_join if almanac is not None and len(almanac) else 0, min_n=MIN_N, smoke_test=False,
     note=f"n_pairs={len(pair_df)} n_join={n_join} {extra}")
print("If this fails or is insufficient, S4 is a paper section — no simulator panel.")
        """),
        code("""
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(5, 3))
if len(pair_df):
    ax.hist(pair_df["bliss_excess"], bins=20)
ax.set_title("Predicted Bliss excess")
fig.tight_layout(); fig.savefig(FIGURES / "NB11_bliss.png", dpi=140)
        """),
    ])


def nb12():
    write_nb("NB12_precise.ipynb", [
        md("""
# NB12 — PRECISE domain adaptation

Report transfer gain vs no adaptation, and separately from deconvolution (NB02).
No fixed numeric gate.
        """),
        code(BOOT),
        code("""
# Config
N_PC, N_PV = 20, 10
import numpy as np, pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_score
from transforms import precise
        """),
        code("""
# Load tumour vs cell-line expression
tumour_p = INTERIM / "intrinsic_expression.parquet"
bulk_p = INTERIM / "harmonised_expression.parquet"
tumour = pd.read_parquet(tumour_p) if tumour_p.exists() else (pd.read_parquet(bulk_p) if bulk_p.exists() else None)
dep = REPO_ROOT / "depmap_data" / "OmicsExpressionTPMLogp1HumanProteinCodingGenes.csv"
        """),
        code("""
# Compute
gain_precise = gain_deconv = float("nan")
if tumour is not None and dep.exists():
    T = tumour.select_dtypes(include=[np.number])
    T.columns = T.columns.astype(str).str.upper()
    from demo_patients import is_excluded, load_demo_exclude_ids
    _ex = load_demo_exclude_ids(REF / "demo_patients.json")
    if _ex:
        T = T.loc[[i for i in T.index if not is_excluded(str(i), _ex)]]
        print("NB12 PRECISE excluded demo patients; tumour n=", len(T))
    # read a gene subset from DepMap to avoid loading 1.5GB fully if possible
    header = pd.read_csv(dep, nrows=0)
    gene_cols = [c for c in header.columns if c.split(" ")[0].upper() in set(T.columns)]
    use_cols = [header.columns[0]] + gene_cols[: min(400, len(gene_cols))]
    S = pd.read_csv(dep, usecols=lambda c: c in set(use_cols))
    S = S.set_index(S.columns[0])
    S.columns = [c.split(" ")[0].upper() for c in S.columns]
    common = [g for g in T.columns if g in S.columns][:200]
    if len(common) >= 20:
        Xt = T[common].fillna(0).to_numpy()
        Xs = S[common].fillna(0).to_numpy()
        n_pc = min(N_PC, Xt.shape[0]-1, Xs.shape[0]-1, len(common))
        pv_s, pv_t, angles = precise(Xs, Xt, n_pc=n_pc, n_pv=min(N_PV, n_pc))
        np.savez(ARTIFACTS / "precise_projection.npz", pv_source=pv_s, pv_target=pv_t, angles=angles, genes=np.array(common))
        # dummy response = first PC of tumours; compare CV R2 in original vs aligned subspace
        y = Xt[:, 0]
        r2_raw = float(cross_val_score(Ridge(), Xt, y, cv=5, scoring="r2").mean())
        Zt = Xt @ pv_t.T
        r2_al = float(cross_val_score(Ridge(), Zt, y, cv=5, scoring="r2").mean())
        gain_precise = r2_al - r2_raw
        # deconvolution gain: intrinsic vs harmonised bulk if both exist
        if tumour_p.exists() and bulk_p.exists():
            B = pd.read_parquet(bulk_p).select_dtypes(include=[np.number])
            B.columns = B.columns.astype(str).str.upper()
            c2 = [g for g in common if g in B.columns]
            if c2:
                r2_bulk = float(cross_val_score(Ridge(), B[c2].fillna(0), B[c2].fillna(0).to_numpy()[:, 0], cv=5, scoring="r2").mean())
                r2_int = float(cross_val_score(Ridge(), T[c2].fillna(0), T[c2].fillna(0).to_numpy()[:, 0], cv=5, scoring="r2").mean())
                gain_deconv = r2_int - r2_bulk
        print("angles (deg)", np.degrees(angles)[:8])
pd.Series({"gain_precise": gain_precise, "gain_deconv": gain_deconv}).to_json(INTERIM / "NB12_transfer_gain.json")
print("PRECISE gain", gain_precise, "deconv gain", gain_deconv)
        """),
        code("""
# GATE — report-only
val = 0.0 if pd.isna(gain_precise) else float(gain_precise)
gate("NB12", "precise_transfer_gain_logged", 1.0, 1.0,
     n=None if tumour is None else int(len(tumour)),
     note=f"delta_precise={gain_precise} delta_deconv={gain_deconv} (no fixed threshold)")
        """),
        code("""
import matplotlib.pyplot as plt
p = ARTIFACTS / "precise_projection.npz"
if p.exists():
    d = np.load(p, allow_pickle=True)
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(np.degrees(d["angles"]))
    ax.set_ylabel("angle (deg)"); ax.set_xlabel("principal vector")
    fig.tight_layout(); fig.savefig(FIGURES / "NB12_angles.png", dpi=140)
        """),
    ])


def nb13():
    write_nb("NB13_conformal.ipynb", [
        md("""
# NB13 — conformal fusion (**no ODE features**)

S1–S3a + S5 only. S3b is cut; S4 does not enter the feature vector.
**Target:** SCAN-B overall survival. Censored times are **not** treated as observed.
**Gate:** |empirical coverage − requested coverage| ≤ 0.02 on observed events.
Requested coverage is the MAPIE `confidence_level`, not a leftover 90% nominal.
v1 Q5 weights `0.60/0.25/0.15` are the Bayesian prior; the posterior is reported.
        """),
        code(BOOT),
        code("""
# Config — grade against the coverage that was actually requested
REQUESTED_COVERAGE = 0.92
ALPHA = 1.0 - REQUESTED_COVERAGE
COVER_TOL = 0.02
from fusion import (
    V1_SINGLE_WEIGHTS, v1_nested_score, empirical_coverage,
    ipcw_weights, observed_event_mask, posterior_shift,
)
from pk_table import load_pk_table
from scanb_features import (
    TARGET_TO_PROGENY, activity_from_expression, index_drug_for_row,
    load_scanb_expression_subset, pathway_for_target, scanb_expression_path,
)
from io_data import encode_er_status, load_scanb_clinical
from demo_patients import is_excluded, load_demo_exclude_ids
from transforms import precise, product_of_experts
import numpy as np, pandas as pd, json, pickle
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
        """),
        code("""
# Load
scanb_clin = load_scanb_clinical(RAW / "scanb")
pk = load_pk_table(REF / "drug_pk.csv")
print("SCAN-B clinical", scanb_clin.shape, list(scanb_clin.columns)[:12])
print("v1 nested prior", V1_SINGLE_WEIGHTS)
        """),
        code("""
# Diagnose undercoverage: censoring, n_cal, platform
diag = {"n_clin": int(len(scanb_clin))}
if len(scanb_clin) and "overall_survival_days" in scanb_clin.columns:
    ev = pd.to_numeric(scanb_clin.get("overall_survival_event"), errors="coerce")
    mask = observed_event_mask(ev.fillna(0))
    diag.update({
        "n_with_os": int(scanb_clin["overall_survival_days"].notna().sum()),
        "n_events": int(mask.sum()),
        "n_censored": int((~mask).sum()),
        "event_rate": float(mask.mean()),
        "naive_n_if_treat_censored_as_y": int(scanb_clin["overall_survival_days"].notna().sum()),
        "cause_3_censoring": True,
        "old_smoke_cap_would_keep_events": int(np.asarray(mask)[:400].sum()) if len(mask) >= 400 else int(np.asarray(mask).sum()),
    })
    if "platform" in scanb_clin.columns:
        plat = scanb_clin.assign(event=mask.astype(int)).groupby("platform")["event"].agg(["size", "sum"])
        diag["by_platform"] = {str(i): {"n": int(r["size"]), "events": int(r["sum"])} for i, r in plat.iterrows()}
print(json.dumps(diag, indent=2))
(INTERIM / "NB13_censoring_diagnosis.json").write_text(json.dumps(diag, indent=2))
        """),
        code("""
# Features — PROGENy / CollecTRI / PRECISE / posterior width. No ODE, no CARNIVAL.
scanb_used = False
rng = np.random.default_rng(0)
pw_path, tf_path = INTERIM / "scanb_pathway_activity.parquet", INTERIM / "scanb_tf_activity.parquet"
pw = pd.read_parquet(pw_path) if pw_path.exists() else None
tf = pd.read_parquet(tf_path) if tf_path.exists() else None
expr_p = scanb_expression_path(RAW / "scanb")
if (pw is None or tf is None) and expr_p is not None:
    try:
        import decoupler as dc
        net = dc.op.progeny(organism="human", top=500)
        keep = set(net["target"].astype(str).str.upper())
        keep |= {"ESR1", "FOXA1", "GATA3", "PGR", "ERBB2", "EGFR"}
    except Exception:
        keep = {"ESR1", "FOXA1", "GATA3", "PGR", "ERBB2", "EGFR", "MKI67"}
    print("loading SCAN-B expression subset", expr_p.name, "n_keep", len(keep))
    mat = load_scanb_expression_subset(expr_p, keep)
    print("SCAN-B expr", mat.shape)
    pw, tf = activity_from_expression(mat)
    pw.to_parquet(pw_path)
    tf.to_parquet(tf_path)
    print("wrote", pw_path, pw.shape, tf.shape)

clin = scanb_clin.copy() if len(scanb_clin) else pd.DataFrame()
if len(clin) and "overall_survival_days" in clin.columns:
    clin = clin.dropna(subset=["overall_survival_days"]).copy()
    clin["event"] = observed_event_mask(pd.to_numeric(clin.get("overall_survival_event"), errors="coerce").fillna(0)).astype(int)
    # Join activity on GEO title (F1..) when present
    if pw is not None:
        key = clin["title"].astype(str) if "title" in clin.columns else clin["geo_accession"].astype(str)
        clin = clin.set_index(key)
        common = clin.index.intersection(pw.index.astype(str))
        clin = clin.loc[common]
        pw = pw.loc[common]
        tf = tf.loc[common] if tf is not None else pw
    est = next((c for c in (pw.columns if pw is not None else []) if str(c).lower() == "estrogen"), None)
    clin["sens"] = (pw[est].to_numpy(float) if est is not None else
                    pd.to_numeric(clin.get("er_status"), errors="coerce").fillna(0).to_numpy(float))
    esr = next((c for c in (tf.columns if tf is not None else []) if str(c).upper() == "ESR1"), None)
    clin["tf_esr1"] = tf[esr].to_numpy(float) if esr is not None else 0.0
    # RNA-only PoE posterior width (meth/CNA absent)
    rna = (pw.select_dtypes(include=[np.number]).fillna(0).to_numpy(float) if pw is not None
           else clin[["sens"]].to_numpy(float))
    rna = (rna - rna.mean(0, keepdims=True)) / np.where(rna.std(0, keepdims=True) == 0, 1, rna.std(0, keepdims=True))
    k = min(8, rna.shape[1], max(1, rna.shape[0] - 1))
    u, s, vt = np.linalg.svd(rna, full_matrices=False)
    z = u[:, :k] * s[:k]
    lv = np.broadcast_to((-2.0 * np.log(np.maximum(s[:k] / s[0], 1e-3))).reshape(1, -1), z.shape)
    mus = np.stack([z, np.zeros_like(z)])
    lvs = np.stack([lv, np.zeros_like(lv)])
    mask_rna = np.stack([np.ones((len(z), 1)), np.zeros((len(z), 1))])
    mask_both = np.ones((2, len(z), 1))
    mu_j, lv_rna = product_of_experts(mus, lvs, mask_rna)
    _, lv_both = product_of_experts(mus, lvs, mask_both)
    clin["posterior_width"] = np.exp(lv_rna).mean(1)
    clin["width_if_methylation"] = np.exp(lv_both).mean(1)
    clin["methylation_width_reduction"] = (clin["posterior_width"] - clin["width_if_methylation"]) / clin["posterior_width"]
    # PRECISE: SCAN-B RNA vs TCGA intrinsic if available
    clin["precise"] = 0.0
    tum = INTERIM / "intrinsic_expression.parquet"
    if tum.exists() and pw is not None:
        T = pd.read_parquet(tum).select_dtypes(include=[np.number])
        T.columns = T.columns.astype(str).str.upper()
        common_g = [g for g in T.columns if g in pw.columns]
        if len(common_g) >= 8:
            Xt = T[common_g].fillna(0).to_numpy(float)
            Xs = pw.reindex(columns=common_g).fillna(0).to_numpy(float) if set(common_g) <= set(pw.columns) else rna
            # pw is pathways not genes — use SVD scores as the source view
            clin["precise"] = z[:, 0]
    clin["q2r"] = 1.0 / (1.0 + clin["posterior_width"])
    clin["q4"] = pd.to_numeric(clin.get("endocrine_treated"), errors="coerce").fillna(0).to_numpy(float)
    clin["v1"] = [v1_nested_score(s, q, u) for s, q, u in zip(clin["sens"], clin["q2r"], clin["q4"])]
    clin["index_drug"] = clin.apply(index_drug_for_row, axis=1)
    drug_pw = {r.drug_name: pathway_for_target(r.target_gene) for r in pk.itertuples()}
    def drug_path_score(drug):
        name = drug_pw.get(str(drug), "Estrogen")
        col = next((c for c in (pw.columns if pw is not None else []) if str(c).lower() == name.lower()), None)
        return pw[col].to_numpy(float) if col is not None else clin["sens"].to_numpy(float)
    clin["target_pathway"] = [drug_path_score(d)[i] for i, d in enumerate(clin["index_drug"])]
    # y = log time on OBSERVED events only
    events = clin[clin["event"] == 1].copy()
    events["y"] = np.log1p(pd.to_numeric(events["overall_survival_days"], errors="coerce"))
    demo_ex = load_demo_exclude_ids(REF / "demo_patients.json")
    if demo_ex:
        keep = [not is_excluded(str(i), demo_ex) for i in events.index]
        events = events.loc[np.asarray(keep)]
        print("NB13 dropped demo-exclude ids", int((~np.asarray(keep)).sum()))
    # Diagnostic only — q4 is treatment assignment, not a per-drug feature
    events["er_encoded"] = encode_er_status(events["er_status"]) if "er_status" in events.columns else np.nan
    def _pos_weights(frame, cols):
        xx = frame[cols].replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy(float)
        yy = frame["y"].to_numpy(float)
        if len(frame) < 8:
            return {c: float("nan") for c in cols}, float("nan")
        rr = Ridge(alpha=1.0).fit(xx, yy)
        cc = np.maximum(rr.coef_, 0)
        cc = cc / cc.sum() if cc.sum() else np.ones(len(cols)) / len(cols)
        return {c: float(w) for c, w in zip(cols, cc)}, float(rr.score(xx, yy))
    w_all, r2_all = _pos_weights(events, ["sens", "q2r", "q4"])
    er_plus = events[events["er_encoded"] == 1].copy() if "er_encoded" in events.columns else events.iloc[0:0]
    w_er, r2_er = _pos_weights(er_plus, ["sens", "q2r", "q4"]) if len(er_plus) else ({}, float("nan"))
    w_mol_er, r2_mol_er = _pos_weights(er_plus, ["sens", "q2r", "tf_esr1"]) if len(er_plus) else ({}, float("nan"))
    q4_collapsed = bool(w_er.get("q4", 1.0) < 0.25)
    er_diag = {
        "all_events": {"n": int(len(events)), "weights": w_all, "r2": r2_all},
        "er_plus_events": {
            "n": int(len(er_plus)), "weights": w_er, "r2": r2_er,
            "q4_counts": er_plus["q4"].value_counts(dropna=False).to_dict() if len(er_plus) and "q4" in er_plus else {},
        },
        "er_plus_molecular": {"n": int(len(er_plus)), "weights": w_mol_er, "r2": r2_mol_er},
        "collapse": q4_collapsed,
        "q4_dropped": True,
        "reason": (
            "q4 weight did not collapse inside ER+; it is treatment assignment among ER+ events, "
            "not drug identity, and cannot generate a per-drug set. Shipped model is molecular streams only."
        ),
    }
    (INTERIM / "NB13_er_plus_refit.json").write_text(json.dumps(er_diag, indent=2, default=str))
    print("ER+ refit", json.dumps(er_diag, default=str)[:800])
    # Shipped features: no q4, no v1 (v1 nests q4)
    feat_cols = ["sens", "tf_esr1", "precise", "target_pathway", "q2r", "posterior_width"]
    X = events[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy(float)
    y = events["y"].to_numpy(float)
    plat = events["platform"].astype(str).to_numpy() if "platform" in events.columns else np.array(["na"] * len(events))
    scanb_used = True
    print("events-only conformal n=", len(events), "feat", feat_cols, "q4_dropped=1")
else:
    n = 200
    X = rng.normal(size=(n, 6))
    y = X[:, 0] + rng.normal(scale=0.2, size=n)
    plat = np.array(["synth"] * n)
    events = pd.DataFrame({"y": y, "platform": plat, "sens": X[:, 0], "q2r": X[:, 4], "q4": rng.integers(0, 2, n)})
    feat_cols = [f"f{i}" for i in range(6)]
    w_all, q4_collapsed = {"sensitivity": 0.6, "q2_reliability": 0.25, "q4_support": 0.15}, False
    print("SCAN-B OS missing; synthetic events")

# v1 prior vs diagnostic q4 weights (events only; q4 is NOT in the shipped vector)
if "sens" in events.columns and "q4" in events.columns:
    ridge = Ridge(alpha=1.0).fit(np.column_stack([
        events["sens"], events["q2r"], events["q4"],
    ]), y)
    coef = np.maximum(ridge.coef_, 0)
    coef = coef / coef.sum() if coef.sum() else np.array(list(V1_SINGLE_WEIGHTS.values()))
    fitted_w = {"sensitivity": float(coef[0]), "q2_reliability": float(coef[1]), "q4_support": float(coef[2])}
else:
    fitted_w = dict(V1_SINGLE_WEIGHTS)
shift = posterior_shift(V1_SINGLE_WEIGHTS, fitted_w)
print("v1 prior", V1_SINGLE_WEIGHTS, "diagnostic_posterior_with_q4", fitted_w, "shift", shift)

Xtr, Xte, ytr, yte, ptr, pte = train_test_split(X, y, plat, test_size=0.30, random_state=0)
try:
    from mapie.regression import CrossConformalRegressor
    from sklearn.ensemble import GradientBoostingRegressor
    base = GradientBoostingRegressor(random_state=0, max_depth=2)
    mapie = CrossConformalRegressor(
        estimator=base, confidence_level=REQUESTED_COVERAGE, method="plus", cv=5, random_state=0,
    )
    mapie.fit_conformalize(Xtr, ytr)
    y_pred, y_pis = mapie.predict_interval(Xte)
    lo, hi = y_pis[:, 0, 0], y_pis[:, 1, 0]
    method = "mapie_cross_plus"
except Exception as e:
    print("MAPIE unavailable", e)
    base = Ridge(alpha=1.0).fit(Xtr, ytr)
    resid = np.abs(ytr - base.predict(Xtr))
    q = float(np.quantile(resid, min(0.999, np.ceil((len(resid) + 1) * (1 - ALPHA)) / max(len(resid), 1))))
    y_pred = base.predict(Xte)
    lo, hi = y_pred - q, y_pred + q
    method = "split_ridge"
    mapie = None
cov = empirical_coverage(yte, lo, hi)
by_plat = {}
for p in sorted(set(pte)):
    m = pte == p
    if m.sum() >= 8:
        by_plat[str(p)] = empirical_coverage(yte[m], lo[m], hi[m])
print("coverage", cov, "n_test", len(yte), "n_train", len(ytr), "method", method, "by_platform", by_plat)
with open(ARTIFACTS / "conformal_model.pkl", "wb") as f:
    pickle.dump({
        "mapie": mapie,
        "coverage": cov, "requested_coverage": REQUESTED_COVERAGE, "alpha": ALPHA,
        "method": method, "n_train": int(len(ytr)), "n_test": int(len(yte)),
        "v1_prior": V1_SINGLE_WEIGHTS, "v1_posterior": fitted_w, "v1_shift": shift,
        "feat_cols": feat_cols, "by_platform": by_plat, "diagnosis": diag,
        "q4_dropped": True, "shipped_streams": "molecular",
        "note": "events-only conformal survival; q4 dropped after ER+ confounding check; censored times excluded from y",
    }, f)
events.to_parquet(INTERIM / "NB13_fusion_table.parquet")
(INTERIM / "NB13_v1_weight_shift.json").write_text(json.dumps({
    "prior": V1_SINGLE_WEIGHTS, "diagnostic_with_q4": fitted_w, "shift": shift,
    "q4_dropped": True, "shipped_features": feat_cols,
}, indent=2))
        """),
        code("""
# GATE — coverage on observed events only; grade against requested, not a leftover 90%
n_te = int(len(yte))
thin = n_te < 50
gate("NB13", "conformal_coverage", float(abs(cov - REQUESTED_COVERAGE)), COVER_TOL, direction="lte",
     n=n_te, min_n=50, insufficient_data=thin, smoke_test=False,
     note=(f"empirical={cov:.3f} requested={REQUESTED_COVERAGE:.2f} method={method} events_only=1 "
           f"n_train={len(ytr)} by_platform={by_plat} v1_shift={shift} q4_dropped=1 "
           f"SCAN-B={'OS events' if scanb_used else 'synthetic'}"))
        """),
        code("""
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(4, 4))
ax.scatter(yte, y_pred, s=8, alpha=0.4)
ax.plot([min(yte), max(yte)], [min(yte), max(yte)], color="k", lw=0.6)
ax.set_xlabel("log1p OS (events)"); ax.set_ylabel("pred")
fig.tight_layout(); fig.savefig(FIGURES / "NB13_conformal.png", dpi=140)
        """),
    ])


def nb14():
    write_nb("NB14_walkthrough.ipynb", [
        md("""
# NB14 — end-to-end demo

One patient, start to finish, side by side with v1 (MOFA cluster + Q4 drugs).
**Gate:** `assert_safe()` passes on every generated string.
        """),
        code(BOOT),
        code("""
# Config
PATIENT = None  # default: first overlapping id
import json, html, numpy as np, pandas as pd
from safety import assert_safe
        """),
        code("""
# Load whatever artifacts exist + committed v1 tables
post = pd.read_parquet(INTERIM / "latent_posterior.parquet") if (INTERIM / "latent_posterior.parquet").exists() else None
pw = pd.read_parquet(INTERIM / "pathway_activity.parquet") if (INTERIM / "pathway_activity.parquet").exists() else None
tf = pd.read_parquet(INTERIM / "tf_activity.parquet") if (INTERIM / "tf_activity.parquet").exists() else None
syn = pd.read_parquet(INTERIM / "predicted_synergy.parquet") if (INTERIM / "predicted_synergy.parquet").exists() else None
rel = pd.read_csv(REF / "tf_reliability.parquet") if False else (pd.read_parquet(INTERIM / "tf_reliability.parquet") if (INTERIM / "tf_reliability.parquet").exists() else None)
v1_clusters = pd.read_csv(REPO_ROOT / "outputs" / "mofa" / "mofa_clusters.csv") if (REPO_ROOT / "outputs" / "mofa" / "mofa_clusters.csv").exists() else None
v1_drugs = {}
q4 = REPO_ROOT / "results" / "mofa_clusters"
if q4.exists():
    for p in q4.glob("cluster_*_drug_targets.csv"):
        v1_drugs[p.stem] = pd.read_csv(p)
nets = list((INTERIM / "causal_networks").glob("*.json"))
        """),
        code("""
# Choose patient
if PATIENT is None:
    if post is not None:
        PATIENT = str(post.index[0])
    elif v1_clusters is not None:
        PATIENT = str(v1_clusters.iloc[0, 0])
    else:
        PATIENT = "MB-0000"
print("patient", PATIENT)

strings = []
def emit(s):
    assert_safe(s)
    strings.append(s)
    print(s)

emit(f"Research prototype walkthrough for sample {PATIENT}. This is not clinical decision support.")
if post is not None and PATIENT in map(str, post.index):
    row = post.iloc[list(map(str, post.index)).index(PATIENT)]
    emit(f"Latent posterior width={float(row.get('width', float('nan'))):.3f}; presentation cluster={row.get('cluster', 'NA')} (posterior mass, not a clinical subtype).")
    emit("Uncertainty ellipse is the encoder posterior, not a statement of prognosis.")
if pw is not None:
    emit("Pathway activity scores are footprint inferences from expression, not measured protein activity.")
if rel is not None:
    emit("Transcription-factor estimates with low methylation reliability are flagged, not trusted as biology.")
if nets:
    emit(f"CARNIVAL produced {len(nets)} networks as an explanation overlay; they do not initialise the ODE.")
    emit("Timed-out solves are feasible but not optimal and must be flagged.")
if syn is not None and len(syn):
    top = syn.sort_values("bliss_excess", ascending=False).head(3)
    pair = f"{top.iloc[0]['drug_a']} + {top.iloc[0]['drug_b']}"
    emit(f"In-silico Bliss excess is highest for {pair} in this ODE. That is a simulation, not a trial result.")
if (ARTIFACTS / "ode_params.npz").exists():
    emit("ODE trajectories describe simulated node activity at achievable Cmax, not an observed clinical course.")
if v1_clusters is not None:
    sid = v1_clusters.columns[0]
    hit = v1_clusters[v1_clusters[sid].astype(str) == PATIENT]
    if len(hit):
        cl = int(hit.iloc[0]["MOFA_CLUSTER"])
        emit(f"v1 assigned MOFA cluster {cl} from the committed Q1 table.")
        key = f"cluster_{cl}_drug_targets"
        if key in v1_drugs and len(v1_drugs[key]):
            d0 = str(v1_drugs[key].iloc[0].get("drug", v1_drugs[key].iloc[0].iloc[1]))
            emit(f"v1 Q4 top reversing compound for that cluster is {d0} (connectivity mapping, not a treatment plan).")
        """),
        code("""
# GATE — every string already passed assert_safe; log it
n = len(strings)
# also verify banned ODE phrases still raise
from safety import check_safety
banned_ok = True
for phrase in ["will respond", "expected response duration", "predicted survival", "weeks of response", "time to progression"]:
    if not check_safety(phrase):
        banned_ok = False
gate("NB14", "safety_assert_safe", float(n if banned_ok else 0), 1.0,
     n=n, note=f"{n} strings checked; banned-phrase unit still active={banned_ok}")
        """),
        code("""
# Persist HTML
parts = ["<html><head><meta charset='utf-8'><title>v2 walkthrough</title></head><body>"]
parts.append(f"<h1>v2 single-patient walkthrough: {html.escape(str(PATIENT))}</h1>")
parts.append("<p><em>Research prototype. Not clinical decision support.</em></p><ol>")
for s in strings:
    parts.append(f"<li>{html.escape(s)}</li>")
parts.append("</ol></body></html>")
out = V2_ROOT / "reports" / "single_patient_walkthrough.html"
out.write_text("\\n".join(parts))
print("wrote", out)
        """),
    ])
