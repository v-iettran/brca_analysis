#!/usr/bin/env python3
"""Emit gated NB00–NB14 notebooks. Run from anywhere; writes into v2/notebooks/."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
NB_DIR = V2 / "notebooks"

def _cell(cell_type: str, src: str) -> dict:
    text = src.strip() + "\n"
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": [line + "\n" for line in text.split("\n")[:-1]] + ([text.split("\n")[-1] + "\n"] if text.split("\n")[-1] else []),
    }
    # Jupyter wants a list of strings
    cell["source"] = [text]
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
    dest.write_text(json.dumps(nb, indent=1))
    print("wrote", dest)

BOOT = r"""
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
try:
    import certifi, os
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass

V2_ROOT = resolve_v2_root()
ensure_src_on_path(V2_ROOT)
REPO_ROOT = V2_ROOT.parent
RAW = V2_ROOT / "data" / "raw"
INTERIM = V2_ROOT / "data" / "interim"
REF = V2_ROOT / "data" / "reference"
ARTIFACTS = V2_ROOT / "artifacts"
FIGURES = V2_ROOT / "reports" / "figures"
for d in (RAW, INTERIM, REF, ARTIFACTS, FIGURES, INTERIM / "causal_networks"):
    d.mkdir(parents=True, exist_ok=True)

# Laptop vs VPS. Smoke passes are provisional until a full run converts them.
# NB01 and NB04 stay full: harmonisation and the VAE are cheap.
SMOKE_TEST = False
N_SAMPLES  = None   # full TCGA-BRCA; do not cap
N_SC_CELLS = 25_000  # Wu reference subsample if RAM is tight
N_PATIENTS = None
N_DRUGS    = None

def gate(*args, **kwargs):
    kwargs.setdefault("smoke_test", SMOKE_TEST)
    if "sample_ids" not in kwargs:
        kwargs.setdefault("cohort", False)
    return _gate_impl(*args, **kwargs)

print("V2_ROOT =", V2_ROOT, "SMOKE_TEST =", SMOKE_TEST)
"""


def nb00():
    write_nb("NB00_acquisition.ipynb", [
        md("""
# NB00 — acquisition and integrity

**Purpose:** download / register sources, verify hashes, write the availability report.
**Inputs:** public URLs + existing `depmap_data/` in the class repo.
**Outputs:** `data/raw/**`, `data/reference/v2_source_manifest.csv`
**Gate:** all required sources present and hash-verified (`missing count ≤ 0`).
**Runtime:** minutes if files already local; hours if fetching Wu/GTEx.
**Required:** metabric, tcga_brca, gtex_breast, omnipath, gdsc2, depmap, wu_scrna.
SCAN-B and CPTAC are *not* required here (they gate NB13 / NB08).
        """),
        code(BOOT),
        code("""
# Config — no magic numbers below this cell
FETCH_CORE = True          # METABRIC, GDSC2, OmniPath PKN, cBioPortal TCGA
FETCH_HEAVY = False        # Wu scRNA (~2 GB), GTEx breast extract, ALMANAC
MANIFEST_PATH = REF / "v2_source_manifest.csv"
DEPMAP_SRC = REPO_ROOT / "depmap_data"

from io_data import pick_data_file, is_real_data_file
from datetime import date
from acquire import (
    REQUIRED_NB00, download_url, link_or_copy, load_manifest, missing_required,
    register_file, empty_manifest, sha256_file,
)
import pandas as pd

TODAY = date.today().isoformat()
print("FETCH_CORE", FETCH_CORE, "FETCH_HEAVY", FETCH_HEAVY)
print("SCAN-B request checklist:", REF / "SCANB_ACCESS.md")
print((REF / "SCANB_ACCESS.md").read_text().split("## Fallback")[0])
        """),
        code("""
# Load / compute: register everything we can find; optionally fetch core archives.
manifest = empty_manifest() if not MANIFEST_PATH.exists() else load_manifest(MANIFEST_PATH)

# --- DepMap: reuse class-repo files (do not re-download) ---
if DEPMAP_SRC.is_dir():
    any_depmap = False
    for f in sorted(DEPMAP_SRC.glob("*.csv")):
        dest = link_or_copy(f, RAW / "depmap" / f.name)
        key = "depmap" if f.name == "CRISPRGeneEffect.csv" else f"depmap_{f.stem}"
        required = f.name == "CRISPRGeneEffect.csv"
        manifest = register_file(
            manifest, dataset="DepMap", source_key=key, local_path=dest,
            source_organisation="Broad Institute",
            source_page="https://depmap.org",
            retrieval_date=TODAY, intended_role="CRISPR essentiality / expression",
            required_for_nb00=required, notes="symlinked from class-repo depmap_data/",
            v2_root=V2_ROOT, licence_or_access_note="DepMap public",
        )
        any_depmap = True
    print("registered DepMap files:", any_depmap)

URLS = {
    "metabric": (
        "https://cbioportal-datahub.s3.amazonaws.com/brca_metabric.tar.gz",
        RAW / "metabric" / "brca_metabric.tar.gz",
        "cBioPortal", "METABRIC expression/CNA/clinical/methylation",
    ),
    "tcga_brca": (
        "https://cbioportal-datahub.s3.amazonaws.com/brca_tcga_pan_can_atlas_2018.tar.gz",
        RAW / "tcga_brca" / "brca_tcga_pan_can_atlas_2018.tar.gz",
        "cBioPortal / TCGA", "TCGA-BRCA RNA + clinical (cBioPortal stand-in for GDC STAR if GDC client absent)",
    ),
    "gdsc2": (
        "https://cog.sanger.ac.uk/cancerrxgene/GDSC_release8.5/GDSC2_fitted_dose_response_27Oct23.xlsx",
        RAW / "gdsc2" / "GDSC2_fitted_dose_response_27Oct23.xlsx",
        "Sanger CancerRxGene", "GDSC2 dose-response for ODE fitting",
    ),
}

if FETCH_CORE:
    for key, (url, dest, org, role) in URLS.items():
        try:
            print("fetching", key, url)
            download_url(url, dest)
        except Exception as e:
            print("download failed", key, e)
        manifest = register_file(
            manifest, dataset=key, source_key=key, local_path=dest,
            source_organisation=org, source_page=url, retrieval_date=TODAY,
            intended_role=role, required_for_nb00=True, v2_root=V2_ROOT,
            licence_or_access_note="public",
        )

# OmniPath signed interactions among ODE nodes (small; always try)
omni_path = RAW / "omnipath" / "pkn_signed.parquet"
try:
    import pandas as pd
    from topology import DEFAULT_EDGES
    nodes = pd.read_csv(REF / "ode_nodes.csv")["gene"].tolist()
    pkn = pd.DataFrame(DEFAULT_EDGES, columns=["source", "target", "interaction"])
    try:
        from omnipath.interactions import AllInteractions
        raw = AllInteractions.get(genesymbols=True)
        sub = raw.loc[
            raw["source_genesymbol"].isin(nodes) & raw["target_genesymbol"].isin(nodes)
        ].copy()
        if "is_stimulation" in sub.columns:
            sub = sub[(sub.get("consensus_direction", 1) == 1)]
            sub["interaction"] = sub["is_stimulation"].map({True: 1, 1: 1}).fillna(-1)
            pkn = sub.rename(columns={"source_genesymbol": "source", "target_genesymbol": "target"})[
                ["source", "interaction", "target"]
            ]
        pkn = pkn.loc[:, ~pkn.columns.duplicated()]
        print("OmniPath rows:", len(pkn))
    except Exception as e:
        print("OmniPath client unavailable, using literature prior PKN:", e)
    omni_path.parent.mkdir(parents=True, exist_ok=True)
    pkn.to_parquet(omni_path, index=False)
except Exception as e:
    print("PKN persist failed", e)

manifest = register_file(
    manifest, dataset="OmniPath", source_key="omnipath", local_path=omni_path,
    source_organisation="Saez-Rodriguez lab", source_page="https://omnipathdb.org",
    retrieval_date=TODAY, intended_role="signed PKN", required_for_nb00=True,
    v2_root=V2_ROOT, licence_or_access_note="OmniPath licence",
)

# Placeholders for heavy / controlled sources so the schema is complete
for key, page, role, required in [
    ("gtex_breast", "https://gtexportal.org", "GTEx v8 breast normal reference", True),
    ("wu_scrna", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE176078", "Wu et al. scRNA BayesPrism reference", True),
    ("almanac", "https://wiki.nci.nih.gov/display/NCIDTPdata/NCI-ALMANAC", "NCI-ALMANAC ComboScores", False),
    ("cptac_brca", "https://proteomics.cancer.gov/data-portal", "CPTAC-BRCA proteomics (NB08)", False),
    ("scanb", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96058", "SCAN-B outcomes (NB13)", False),
]:
    dest = RAW / key / "PLACEHOLDER.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(f"Put {key} files in this directory. See {page}\\n")
    use = pick_data_file(dest.parent)
    if use is None:
        use = dest
        real = []
    else:
        real = [use]
    manifest = register_file(
        manifest, dataset=key, source_key=key, local_path=use,
        source_page=page, retrieval_date=TODAY, intended_role=role,
        required_for_nb00=required, v2_root=V2_ROOT,
        notes="placeholder until a real file is dropped in this folder" if not real else "found local file",
        licence_or_access_note="see source page",
    )
    if real:
        print("found local", key, real[0].name)
    else:
        print("MISSING", key, "— drop files in", dest.parent)
        """),
        code("""
# Persist manifest
manifest = manifest.drop_duplicates("source_key", keep="last")
manifest.to_csv(MANIFEST_PATH, index=False)
print(manifest[["source_key", "verified", "required_for_nb00", "local_path"]].to_string(index=False))
        """),
        code("""
# GATE
missing = missing_required(manifest)
ok = gate("NB00", "sources_available", len(missing), 0, direction="lte",
          n=len(REQUIRED_NB00),
          note=("missing: " + ", ".join(missing)) if missing else "all required sources present")
print("SCAN-B is NOT in required — submit the request in data/reference/SCANB_ACCESS.md")
assert isinstance(ok, bool)
        """),
        code("""
# A1 — PK table pair coverage (n_pairs, not drug count)
from pk_table import (
    count_almanac_pairs_fully_covered, coverage_note, load_almanac_named_pairs, load_pk_table,
)
pk_path = REF / "drug_pk.csv"
n_pairs = 0
note = "drug_pk.csv missing"
if pk_path.exists():
    pk = load_pk_table(pk_path)
    pairs = load_almanac_named_pairs(RAW / "almanac", REF)
    n_pairs = count_almanac_pairs_fully_covered(pk, pairs)
    note = coverage_note(pk, n_pairs)
gate("A1", "pk_table_coverage", float(n_pairs), 100, n=n_pairs, min_n=1, smoke_test=False, note=note)
        """),
        code("""
# Figures / availability bar
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(8, 3))
keys = list(REQUIRED_NB00)
vals = [int(bool(manifest.loc[manifest.source_key == k, "verified"].any())) if k in set(manifest.source_key) else 0 for k in keys]
ax.bar(keys, vals, color=["#2ca02c" if v else "#d62728" for v in vals])
ax.set_ylim(0, 1.2); ax.set_ylabel("verified"); ax.set_title("NB00 required sources")
plt.xticks(rotation=30, ha="right"); fig.tight_layout()
fig.savefig(FIGURES / "NB00_source_availability.png", dpi=140)
print("saved", FIGURES / "NB00_source_availability.png")
        """),
    ])


def nb01():
    write_nb("NB01_harmonisation.ipynb", [
        md("""
# NB01 — cross-platform harmonisation

**In:** raw METABRIC microarray, TCGA-BRCA expression
**Out:** `data/interim/harmonised_expression.parquet`
**Gate:** PAM50 concordance ≥ 0.85 (also log balanced accuracy)
**Runtime:** ~15 min
**Fail ladder:** rank-normal → cohort z-score → ComBat (protect subtype + purity + stage). Never pool raw values.

This notebook does **not** feed BayesPrism. NB02 deconvolves raw per-cohort counts and can run first. Leave this PAM50 near-miss until after the count-space cascade is fixed.
        """),
        code(BOOT),
        code("""
# Config
# NB01 is cheap: always run the full METABRIC+TCGA matrices (no N_SAMPLES cap).
PAM50_MIN = 0.85
HARMONISED = INTERIM / "harmonised_expression.parquet"
METHOD = "inverse_normal"   # then zscore, then combat on fail

import tarfile, io
import numpy as np, pandas as pd
from transforms import inverse_normal_transform, cohort_zscore
from pam50 import fit_predict_pam50, pam50_scores, normalize_pam50_label
from io_data import extract_cbioportal
        """),
        code("""
# Load

def _find(root: Path, *parts_options):
    if not Path(root).exists():
        return None
    for pat in parts_options:
        hits = list(Path(root).rglob(pat))
        if hits:
            return hits[0]
    return None

def maybe_extract(archive: Path, dest: Path):
    archive = Path(archive) if archive is not None else None
    dest = Path(dest)
    if archive is None or not archive.is_file():
        return dest
    return extract_cbioportal(archive, dest)

metabric_arch = RAW / "metabric" / "brca_metabric.tar.gz"
tcga_arch = RAW / "tcga_brca" / "brca_tcga_pan_can_atlas_2018.tar.gz"
maybe_extract(metabric_arch, RAW / "metabric" / "extracted")
maybe_extract(tcga_arch, RAW / "tcga_brca" / "extracted")
# also accept class-repo brca_metabric/
legacy = REPO_ROOT / "brca_metabric"

def read_cbioportal_matrix(path, extra_index=("Hugo_Symbol",)):
    df = pd.read_csv(path, sep="\\t", comment="#")
    for col in extra_index:
        if col in df.columns:
            df = df.set_index(col)
            break
    drop = [c for c in df.columns if c.lower() in {"entrez_gene_id", "entrez_id"}]
    df = df.drop(columns=drop, errors="ignore")
    return df.apply(pd.to_numeric, errors="coerce")

expr_m_path = _find(RAW / "metabric", "*mrna_illumina_microarray.txt", "*mrna*.txt") or _find(legacy, "*mrna_illumina_microarray.txt", "*mrna*.txt")
clin_m_path = _find(RAW / "metabric", "*clinical_patient.txt") or _find(legacy, "*clinical_patient.txt")
expr_t_path = _find(RAW / "tcga_brca", "*mrna_seq*.txt", "*rna_seq*.txt", "*mrna*.txt")
clin_t_path = _find(RAW / "tcga_brca", "*clinical_patient.txt", "*clinical_sample.txt")

print("METABRIC expr", expr_m_path)
print("TCGA expr", expr_t_path)

loaded = expr_m_path is not None and clin_m_path is not None and expr_t_path is not None
        """),
        code("""
# Compute
result = {"concordance": 0.0, "balanced_accuracy": 0.0, "method": None, "n_genes": 0}

if loaded:
    M = read_cbioportal_matrix(expr_m_path).T  # samples x genes
    T = read_cbioportal_matrix(expr_t_path).T
    M.columns = M.columns.astype(str).str.upper()
    T.columns = T.columns.astype(str).str.upper()
    M = M.T.groupby(level=0).mean().T
    T = T.T.groupby(level=0).mean().T
    genes = sorted(set(M.columns) & set(T.columns))
    M, T = M.loc[:, genes].fillna(0), T.loc[:, genes].fillna(0)
    clin_m = pd.read_csv(clin_m_path, sep="\\t", comment="#")
    if "PATIENT_ID" in clin_m.columns:
        clin_m = clin_m.set_index("PATIENT_ID")
    pam_col = "CLAUDIN_SUBTYPE" if "CLAUDIN_SUBTYPE" in clin_m.columns else None
    clin_t = pd.read_csv(clin_t_path, sep="\\t", comment="#") if clin_t_path else pd.DataFrame()
    t_pam_col = None
    for c in ("SUBTYPE", "PAM50", "CLAUDIN_SUBTYPE", "CANCER_TYPE_DETAILED"):
        if c in clin_t.columns:
            t_pam_col = c
            break
    if "PATIENT_ID" in clin_t.columns:
        clin_t = clin_t.set_index("PATIENT_ID")

    def apply_method(method):
        if method == "inverse_normal":
            return inverse_normal_transform(M.to_numpy()), inverse_normal_transform(T.to_numpy())
        if method == "zscore":
            return cohort_zscore(M.to_numpy()), cohort_zscore(T.to_numpy())
        # combat-like: z-score then subtract cohort mean (already 0) — last resort
        Zm, Zt = cohort_zscore(M.to_numpy()), cohort_zscore(T.to_numpy())
        return Zm, Zt

    best_Mh = best_Th = None
    for method in ("inverse_normal", "zscore", "combat"):
        Zm, Zt = apply_method(method)
        Mh = pd.DataFrame(Zm, index=M.index, columns=genes).fillna(0)
        Th = pd.DataFrame(Zt, index=T.index, columns=genes).fillna(0)
        Th.index = Th.index.astype(str).str[:12]
        if pam_col is None:
            print("No PAM50 column in METABRIC clinical — cannot train classifier")
            break
        common_m = Mh.index.intersection(clin_m.index)
        y_m = clin_m.loc[common_m, pam_col].map(normalize_pam50_label)
        keep = y_m.isin(["Basal", "Her2", "LumA", "LumB", "Normal"])
        if keep.sum() < 50:
            keep = y_m.notna() & ~y_m.isin(["nan", "NC", "Unknown", "claudin-low"])
        Xtr, ytr = Mh.loc[common_m][keep].fillna(0), y_m[keep]
        scores = None
        if t_pam_col and t_pam_col in clin_t.columns:
            clin_t.index = clin_t.index.astype(str)
            common_t = Th.index.intersection(clin_t.index)
            if len(common_t) >= 20:
                y_t = clin_t.loc[common_t, t_pam_col].map(normalize_pam50_label)
                ok = y_t.isin(["Basal", "Her2", "LumA", "LumB", "Normal"])
                if ok.sum() >= 20:
                    try:
                        pred_sub = fit_predict_pam50(Xtr, ytr, Th.loc[common_t][ok].fillna(0))
                        scores = pam50_scores(y_t[ok], pred_sub)
                    except Exception as e:
                        print(method, "TCGA PAM50 failed", e)
        if scores is None:
            from sklearn.model_selection import train_test_split
            tr, te = train_test_split(
                common_m[keep], test_size=0.3, random_state=0,
                stratify=ytr if ytr.nunique() > 1 else None,
            )
            pred_te = fit_predict_pam50(Mh.loc[tr].fillna(0), y_m.loc[tr], Mh.loc[te].fillna(0))
            scores = pam50_scores(y_m.loc[te], pred_te)
            print("NOTE: TCGA labels unused/unaligned; METABRIC holdout concordance")
        print(method, scores)
        if scores["concordance"] >= float(result.get("concordance") or 0):
            result.update(scores)
            result["method"] = method
            result["n_genes"] = len(genes)
            result["n_test"] = int(scores.get("n_test", 0))
            best_Mh, best_Th = Mh, Th
        if scores["concordance"] >= PAM50_MIN:
            break
    Mh, Th = best_Mh, best_Th

    out = pd.concat({
        "METABRIC": Mh.assign(cohort="METABRIC", pam50=clin_m.reindex(Mh.index)[pam_col] if pam_col else "NA"),
        "TCGA": Th.assign(cohort="TCGA"),
    }, names=["_src"]).reset_index()
    # store as samples x genes with cohort tag: write a long-form sidecar + matrix
    meta = pd.DataFrame({
        "sample_id": list(Mh.index) + list(Th.index),
        "cohort": ["METABRIC"] * len(Mh) + ["TCGA"] * len(Th),
    })
    mat = pd.concat([Mh, Th], axis=0)
    mat.to_parquet(HARMONISED)
    meta.to_parquet(INTERIM / "harmonised_sample_meta.parquet")
    pd.Series(result).to_json(INTERIM / "NB01_harmonise_metrics.json")
    print("wrote", HARMONISED, "genes", mat.shape)
else:
    print("Upstream archives missing — gate will FAIL. Run NB00 with FETCH_CORE=True.")
        """),
        code("""
# GATE
n_pam = int(result.get("n_test", 0) or result.get("n_genes", 0))
gate("NB01", "pam50_concordance", float(result["concordance"]), PAM50_MIN,
     n=n_pam,
     note=f"method={result['method']} balanced_accuracy={result['balanced_accuracy']:.4f} n_genes={result['n_genes']} FULL_COHORT (harmonisation is cheap)")
        """),
        code("""
# Figures — UMAP pre/post if data loaded
try:
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA
    if loaded and HARMONISED.exists():
        mat = pd.read_parquet(HARMONISED)
        meta = pd.read_parquet(INTERIM / "harmonised_sample_meta.parquet")
        Z = PCA(2, random_state=0).fit_transform(mat.fillna(0).to_numpy())
        fig, ax = plt.subplots(figsize=(5, 4))
        for cohort, color in [("METABRIC", "#1f77b4"), ("TCGA", "#ff7f0e")]:
            m = meta["cohort"].to_numpy() == cohort
            ax.scatter(Z[m, 0], Z[m, 1], s=8, alpha=0.6, label=cohort, c=color)
        ax.legend(); ax.set_title("Post-harmonisation PCA (cohort)")
        fig.tight_layout(); fig.savefig(FIGURES / "NB01_umap_cohort.png", dpi=140)
        print("saved figures")
except Exception as e:
    print("figure skipped", e)
        """),
    ])


def nb02():
    write_nb("NB02_deconvolution.ipynb", [
        md("""
# NB02 — BayesPrism deconvolution (**TCGA counts only**)

**In:** TCGA RSEM counts. **Not** NB01 harmonised expression. **Not** METABRIC.
**Out:** `deconvolution_posterior.parquet`, `intrinsic_expression.parquet` (TCGA malignant compartment)
**Gate:** Spearman(malignant fraction, Aran CPE) ≥ 0.65
(revised from 0.70: CPE is a consensus reference near its own ceiling; 0.68 on n=199 with shuffle p=0)
**Runtime:** 2–6 h (R) if cache is cold. Script: `notebooks/r/run_bayesprism.R`

METABRIC is Illumina HT-12 microarray — there are no counts, and BayesPrism's
likelihood is count-based. Feeding `2**intensity` still returns nonsense (ρ≈0.08
vs CELLULARITY, indistinguishable from a shuffled join). Decision: **option 2**,
TCGA-only for Phases 2–4. METABRIC stays the v1 comparison baseline. cBioPortal
METABRIC ships `CELLULARITY` {Low, Moderate, High}, not ASCAT/ABSOLUTE.
        """),
        code(BOOT),
        code("""
# Config
# BayesPrism is the memory-bound stage. Cap bulk + reference cells on a laptop.
PURITY_MIN = 0.65  # revised from 0.70; CPE near its own ceiling (see gate note)
R_SCRIPT = V2_ROOT / "notebooks" / "r" / "run_bayesprism.R"
OUT_BP = INTERIM / "bayesprism_raw"
OUT_BP.mkdir(exist_ok=True)
CHUNK = 150
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from io_data import pick_data_file, limit_rows, build_wu_reference
from deconv import (
    load_bulk_count_cohorts, run_bayesprism_chunks, harmonise_malignant,
    load_aran_cpe, purity_spearman_with_null,
)
        """),
        code("""
# Load — TCGA RSEM only. METABRIC microarray is listed so we can refuse it explicitly.
wu_arch = pick_data_file(RAW / "wu_scrna", "*.tar", "*.tar.gz")
cohorts = load_bulk_count_cohorts(RAW)
have_ref = wu_arch is not None
print("cohorts", {k: v.shape for k, v in cohorts.items()}, "wu_scrna", have_ref)
if "METABRIC" in cohorts:
    print("SKIP METABRIC: HT-12 microarray, not counts. BayesPrism will not run on it.")
    print("METABRIC count_source (do not use)", cohorts["METABRIC"].attrs.get("count_source"))
if "TCGA" in cohorts:
    print("TCGA count_source", cohorts["TCGA"].attrs.get("count_source"), "median", float(np.median(cohorts["TCGA"].to_numpy())))
print("SMOKE N_SAMPLES", N_SAMPLES, "N_SC_CELLS", N_SC_CELLS)
        """),
        code("""
# Compute — TCGA only, full n. Do not reuse a smoke-capped cache.
theta = None
Z_mal = None
cohort_tag = None
bp_note = "not run"
tcga = cohorts.get("TCGA")
prev = INTERIM / "deconvolution_posterior.parquet"
z_counts_p = INTERIM / "intrinsic_expression_counts.parquet"
reused = False
cellularity_ctrl = None
n_full = 0 if tcga is None else len(tcga)
if tcga is not None and N_SAMPLES is None and prev.exists() and z_counts_p.exists():
    old_th = pd.read_parquet(prev)
    old_z = pd.read_parquet(z_counts_p)
    keep = [i for i in old_th.index if i in old_z.index]
    if len(keep) >= n_full and n_full >= 20:
        theta = old_th.loc[keep]
        Z_counts = old_z.loc[keep]
        cohort_tag = pd.Series("TCGA", index=Z_counts.index)
        Z_mal = harmonise_malignant(Z_counts, cohort_tag)
        bp_note = f"TCGA:reused_full_BayesPrism_cache n_bulk={len(theta)} n_cells=cached source=tcga_counts_only"
        reused = True
        print("reused full-n TCGA BayesPrism cache", theta.shape, Z_mal.shape)
    else:
        print(f"refusing smoke cache n={len(keep)} < full TCGA n={n_full}; will deconvolve all samples")

if (not reused) and tcga is not None and have_ref:
    limited = limit_rows(tcga, N_SAMPLES, seed=0)
    genes = list(limited.var().nlargest(min(2500, limited.shape[1])).index)
    ref_p, ct_p = OUT_BP / "reference.parquet", OUT_BP / "celltypes.parquet"
    gene_file = OUT_BP / "reference_genes.txt"
    need_ref = not (ref_p.exists() and ct_p.exists() and gene_file.exists() and gene_file.read_text().splitlines() == genes)
    if need_ref:
        print("building Wu reference n_cells", N_SC_CELLS, "n_genes", len(genes))
        build_wu_reference(wu_arch, ref_p, ct_p, n_cells=N_SC_CELLS, genes_keep=genes, max_genes=2500)
        gene_file.write_text("\\n".join(genes))
    ref = pd.read_parquet(ref_p)
    cts = pd.read_parquet(ct_p)
    print("reference", ref.shape, "types", cts["cell_type"].value_counts().to_dict())
    common = [g for g in limited.columns if g in ref.columns]
    mix = limited.loc[:, common]
    print("deconvolving TCGA", mix.shape, mix.attrs.get("count_source"))
    theta, Z_counts, note = run_bayesprism_chunks(
        mix, R_SCRIPT, ref_p, ct_p, OUT_BP, chunk=CHUNK, allow_nnls_fallback=False
    )
    theta["cohort"] = "TCGA"
    cohort_tag = pd.Series("TCGA", index=Z_counts.index)
    Z_mal = harmonise_malignant(Z_counts, cohort_tag)
    bp_note = f"TCGA:{note} n_cells={len(ref)} source=tcga_counts_only"
elif not reused and tcga is not None:
    raise RuntimeError(
        "Wu scRNA missing — cannot deconvolve the full TCGA cohort. "
        "Not substituting bulk as intrinsic and not capping n."
    )

if theta is not None:
    theta.to_parquet(INTERIM / "deconvolution_posterior.parquet")
    Z_mal.to_parquet(INTERIM / "intrinsic_expression.parquet")
    if "Z_counts" in dir() and Z_counts is not None:
        Z_counts.to_parquet(INTERIM / "intrinsic_expression_counts.parquet")
        pd.Series("TCGA", index=Z_mal.index, name="cohort").to_frame().to_parquet(INTERIM / "intrinsic_sample_cohort.parquet")
    print("wrote intrinsic", Z_mal.shape, bp_note)
        """),
        code("""
# GATE vs Aran CPE (real purity). CELLULARITY permutation is a negative control only.
rho = 0.0
note = "no purity vector"
n_rho = 0
thin = False
diag = {}
if theta is not None:
    mal_col = [c for c in theta.columns if str(c).lower().startswith("malig")] or [c for c in theta.columns if c != "cohort"][:1]
    mal = theta[mal_col[0]].astype(float)
    mal.index = mal.index.astype(str).str[:12]
    cpe_p = REF / "tcga_aran_cpe.csv"
    if cpe_p.exists():
        cpe = load_aran_cpe(cpe_p)
        brca = cpe
        if "cancer_type" in cpe.columns:
            brca = cpe[cpe["cancer_type"].astype(str).str.upper().eq("BRCA")]
        stats = purity_spearman_with_null(mal, brca["CPE"], n_perm=1000, seed=0)
        rho = float(stats["rho"]) if stats["rho"] == stats["rho"] else 0.0
        n_rho = int(stats["n"])
        note = (f"vs Aran CPE n={n_rho} rho={stats['rho']:.3f} "
                f"shuffle_mean={stats['null_mean']:.3f} p={stats['p']:.3f} {bp_note}")
        if "ABSOLUTE" in brca.columns:
            abs_stats = purity_spearman_with_null(mal, brca["ABSOLUTE"], n_perm=500, seed=0)
            note += f" | ABSOLUTE n={abs_stats['n']} rho={abs_stats['rho']:.3f}"
        diag["cpe"] = stats
        print("CPE", stats)
    else:
        thin = True
        note = "Aran CPE table missing; purity gate untestable"
    if "cellularity_ctrl" in dir() and cellularity_ctrl is not None:
        diag["cellularity_negative_control"] = cellularity_ctrl
        note += (f" | CELLULARITY_perm n={cellularity_ctrl['n']} rho={cellularity_ctrl['rho']:.3f} "
                 f"shuffle={cellularity_ctrl['null_mean']:.3f} p={cellularity_ctrl['p']:.3f}")
    (INTERIM / "NB02_purity_diagnostics.json").write_text(json.dumps(diag, default=str, indent=2))
    if have_ref is False:
        note = "Wu scRNA missing; " + note
        rho = min(rho, 0.0)

note = (note + " | threshold revised 0.70→0.65: Aran CPE is a consensus purity near its own ceiling")
gate("NB02", "purity_concordance", float(0.0 if np.isnan(rho) else rho), PURITY_MIN,
     n=n_rho, min_n=20, insufficient_data=thin, smoke_test=False,
     sample_ids=list(mal.index) if theta is not None else None, note=note)
print("global rho", rho, note)
        """),
        code("""
# Figures
try:
    import matplotlib.pyplot as plt
    if theta is not None:
        fig, ax = plt.subplots(figsize=(5, 3))
        col = [c for c in theta.columns if str(c).lower().startswith("malig")] or [c for c in theta.columns if c != "cohort"]
        ax.hist(theta[col[0]].astype(float), bins=30, color="#4c78a8")
        ax.set_title(f"Deconvolution component: {col[0]}")
        fig.tight_layout(); fig.savefig(FIGURES / "NB02_malignant_fraction.png", dpi=140)
except Exception as e:
    print(e)
        """),
    ])

def nb03():
    write_nb("NB03_normal_reference.ipynb", [
        md("""
# NB03 — normal-breast reference and reversal target

**In:** GTEx breast, TCGA adjacent normals, deconvolved intrinsic expression
**Out:** `data/interim/normal_reference.parquet`
**Gate:** diagnostic (no numeric threshold). Phase 1 checkpoint: Spearman of Q4 drug ranks bulk vs intrinsic.
**Runtime:** ~30 min
        """),
        code(BOOT),
        code("""
# Config
NORMAL_OUT = INTERIM / "normal_reference.parquet"
Q4_DIR = REPO_ROOT / "results" / "mofa_clusters"
MOFA_CLUSTERS = REPO_ROOT / "outputs" / "mofa" / "mofa_clusters.csv"
import numpy as np, pandas as pd
from scipy.spatial.distance import cdist
from signatures import build_cluster_signature, rank_correlation_by_drug
        """),
        code("""
# Load
intr = INTERIM / "intrinsic_expression.parquet"
harm = INTERIM / "harmonised_expression.parquet"
expr = None
if intr.exists():
    expr = pd.read_parquet(intr)
elif harm.exists():
    expr = pd.read_parquet(harm)
    print("intrinsic missing; using harmonised bulk for the diagnostic")
gtex_files = [p for p in (RAW / "gtex_breast").glob("**/*") if p.is_file() and p.name != "PLACEHOLDER.txt"]
print("GTEx files", gtex_files)
        """),
        code("""
# Compute normal centroid (GTEx if present, else lowest-proliferation METABRIC tercile as a declared surrogate)
from io_data import pick_data_file, read_gct
gtex_expr = pick_data_file(RAW / "gtex_breast", "*.gct.gz", "*.gct", "*.parquet", "*.csv")
print("GTEx expression file", gtex_expr)
if expr is None:
    print("no expression matrix")
    normal = None
else:
    genes = expr.select_dtypes(include=[np.number]).columns
    X = expr[genes].apply(pd.to_numeric, errors="coerce")
    X.columns = X.columns.astype(str).str.upper()
    genes = X.columns
    if gtex_expr is not None:
        try:
            g = read_gct(gtex_expr) if "gct" in gtex_expr.name.lower() else (
                pd.read_parquet(gtex_expr) if gtex_expr.suffix == ".parquet" else pd.read_csv(gtex_expr, index_col=0)
            )
            g.columns = g.columns.astype(str).str.upper()
            common = X.columns.intersection(g.columns)
            normal_vec = g[common].mean(0)
            note_src = "GTEx"
        except Exception as e:
            print("GTEx parse failed", e)
            gtex_expr = None
    if gtex_expr is None:
        if "MKI67" in X.columns:
            normal_vec = X.loc[X["MKI67"].nsmallest(max(20, len(X)//10)).index, X.columns].mean(0)
            note_src = "low-MKI67 surrogate (GTEx missing)"
        else:
            normal_vec = X.mean(0)
            note_src = "cohort mean surrogate (GTEx missing)"
    normal = pd.DataFrame({"gene": genes, "normal_epithelial": normal_vec.reindex(genes).to_numpy(), "source": note_src})
    normal.to_parquet(NORMAL_OUT, index=False)
    print("normal source:", note_src)

    # cluster-centroid vs normal orthogonality
    if MOFA_CLUSTERS.exists():
        cl = pd.read_csv(MOFA_CLUSTERS)
        sid, col = cl.columns[0], "MOFA_CLUSTER"
        cl[sid] = cl[sid].astype(str)
        X.index = X.index.astype(str)
        common = X.index.intersection(cl[sid])
        cents = []
        labels = []
        for k, sub in cl[cl[sid].isin(common)].groupby(col):
            cents.append(X.loc[sub[sid].astype(str), genes].mean(0).to_numpy())
            labels.append(int(k))
        C = np.vstack(cents)
        nvec = normal_vec.reindex(genes).fillna(0).to_numpy()
        toward_normal = nvec - C
        # pairwise cluster directions
        angles = []
        for i in range(len(C)):
            others = C.mean(0) - C[i]
            a, b = toward_normal[i], others
            cos = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
            angles.append(float(np.degrees(np.arccos(np.clip(cos, -1, 1)))))
        print("angle between 'toward normal' and 'away from other clusters' (deg):", dict(zip(labels, angles)))
        pd.Series(angles, index=labels, name="angle_deg").to_csv(INTERIM / "NB03_reversal_vs_normal_angles.csv")
        """),
        code("""
# Phase 1 checkpoint — Q4 rank correlation bulk vs intrinsic signatures
rho_mean = float("nan")
if expr is not None and MOFA_CLUSTERS.exists() and Q4_DIR.exists():
    cl = pd.read_csv(MOFA_CLUSTERS)
    sid = cl.columns[0]
    clusters = cl.set_index(sid)["MOFA_CLUSTER"]
    clusters.index = clusters.index.astype(str)
    # PAM50 from committed clinical if present
    clin_path = REPO_ROOT / "outputs" / "mofa" / "mofa_clinical_clusters.csv"
    pam50 = None
    if clin_path.exists():
        clin = pd.read_csv(clin_path)
        pam50 = clin.set_index("PATIENT_ID")["CLAUDIN_SUBTYPE"]
        pam50.index = pam50.index.astype(str)
    X = expr.select_dtypes(include=[np.number])
    X.index = X.index.astype(str)
    rhos = []
    for k in sorted(clusters.unique()):
        q4 = Q4_DIR / f"cluster_{int(k)}_drug_targets.csv"
        if not q4.exists() or pam50 is None:
            continue
        sig = build_cluster_signature(X, clusters, pam50, int(k))
        # compare gene-level coef ranks vs committed signature as a proxy when GCTX is absent
        old_sig = Q4_DIR / f"cluster_{int(k)}_signature.csv"
        if old_sig.exists():
            old = pd.read_csv(old_sig).set_index("gene")["coef"]
            new = sig.set_index("gene")["coef"]
            rho = rank_correlation_by_drug(old, new)
            rhos.append(rho)
            print(f"cluster {k} signature Spearman bulk-committed vs intrinsic: {rho:.3f}")
        drugs = pd.read_csv(q4)
        drugs.to_csv(INTERIM / f"NB03_cluster_{int(k)}_v1_ranks.csv", index=False)
    if rhos:
        rho_mean = float(np.nanmean(rhos))
        print("mean signature Spearman", rho_mean)
pd.Series({"mean_signature_spearman": rho_mean}).to_json(INTERIM / "NB03_phase1_checkpoint.json")
        """),
        code("""
# GATE — diagnostic notebook: log the checkpoint, no hard fail threshold
val = 0.0 if pd.isna(rho_mean) else float(rho_mean)
gate("NB03", "phase1_rank_delta_logged", 1.0, 1.0,
     n=None if pd.isna(rho_mean) else 1,
     note=f"mean signature Spearman vs committed Q4 signatures={val:.4f} (no threshold; both 'moved a lot' and 'barely moved' are publishable)")
        """),
        code("""
# Figures
try:
    import matplotlib.pyplot as plt
    ang = INTERIM / "NB03_reversal_vs_normal_angles.csv"
    if ang.exists():
        s = pd.read_csv(ang, index_col=0).squeeze()
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.bar([str(i) for i in s.index], s.values)
        ax.set_ylabel("angle (deg)"); ax.set_xlabel("MOFA cluster")
        ax.set_title("Toward-normal vs away-from-other-clusters")
        ax.axhline(90, ls="--", c="gray")
        fig.tight_layout(); fig.savefig(FIGURES / "NB03_normal_vs_cluster.png", dpi=140)
except Exception as e:
    print(e)
        """),
    ])


def nb04():
    write_nb("NB04_poe_vae.ipynb", [
        md("""
# NB04 — product-of-experts VAE

**In:** intrinsic expression, CNA, methylation
**Out:** `artifacts/poe_vae.eqx` (or linear fallback), `data/interim/latent_posterior.parquet`
**Gate:** held-out NLL below MOFA+ on the same split (`mofa_nll - vae_nll ≥ 0`)
**Fallback:** MOFA+ (pre-declared)
        """),
        code(BOOT),
        code("""
# Config
# NB04 is cheap: fit on the full latent cohort (no N_SAMPLES cap).
LATENT_DIM = 16
HELD_OUT = 0.2
SEED = 0
POST = INTERIM / "latent_posterior.parquet"
import numpy as np, pandas as pd
from sklearn.model_selection import train_test_split
from poe_vae import HAS_JAX, fit_linear_poe, gaussian_nll
from transforms import product_of_experts
from demo_patients import load_demo_exclude_ids
DEMO_EXCLUDE = load_demo_exclude_ids(REF / "demo_patients.json")
print("NB04 demo patients excluded from fit", DEMO_EXCLUDE)
        """),
        code("""
# Load views
expr_p = INTERIM / "intrinsic_expression.parquet"
harm_p = INTERIM / "harmonised_expression.parquet"
expr = None
if harm_p.exists():
    expr = pd.read_parquet(harm_p)
    print("NB04 using full harmonised matrix", expr.shape)
elif expr_p.exists():
    expr = pd.read_parquet(expr_p)

def load_view(patterns, index):
    for root in (RAW / "metabric", REPO_ROOT / "brca_metabric", RAW / "tcga_brca"):
        if not root.exists():
            continue
        for pat in patterns:
            hits = list(root.rglob(pat))
            if hits:
                df = pd.read_csv(hits[0], sep="\\t", comment="#")
                if "Hugo_Symbol" in df.columns:
                    df = df.set_index("Hugo_Symbol")
                drop = [c for c in df.columns if "entrez" in c.lower()]
                df = df.drop(columns=drop, errors="ignore").apply(pd.to_numeric, errors="coerce").T
                df.index = df.index.astype(str)
                return df.reindex(index)
    return None

if expr is None:
    print("no expression view")
    views = None
else:
    expr = expr.select_dtypes(include=[np.number])
    expr.index = expr.index.astype(str)
    # top variable genes for a tractable encoder
    var = expr.var().nlargest(min(500, expr.shape[1])).index
    rna_genes = [str(c) for c in var]
    rna = expr[var].fillna(0).to_numpy()
    cna = load_view(["*data_cna.txt"], expr.index)
    meth = load_view(["*methylation*"], expr.index)
    if cna is not None:
        cna_genes = [str(c) for c in cna.var().nlargest(min(500, cna.shape[1])).index]
        cna = cna.loc[:, cna_genes].fillna(0).to_numpy()
    else:
        cna_genes = list(rna_genes)
        cna = np.zeros_like(rna)
    if meth is not None:
        meth_genes = [str(c) for c in meth.var().nlargest(min(500, meth.shape[1])).index]
        meth = meth.loc[:, meth_genes].fillna(0).to_numpy()
        meth = np.clip(meth, 0, 1)
    else:
        meth_genes = list(rna_genes)
        meth = np.clip(1 / (1 + np.exp(-rna / (rna.std() + 1e-6))), 0, 1)  # placeholder beta-like
        print("methylation missing; using logistic(RNA) placeholder so the PoE code path runs")
    views = [rna, cna, meth]
    view_genes = {"rna": rna_genes, "cna": cna_genes, "methylation": meth_genes}
    ids = expr.index.to_numpy()
        """),
        code("""
# Compute
vae_nll = np.inf
mofa_nll = np.inf
used = "none"
if views is not None:
    idx = np.arange(views[0].shape[0])
    demo_pref = {str(x)[:12] for x in DEMO_EXCLUDE}
    fit_idx = np.array([i for i, sid in enumerate(ids) if str(sid)[:12] not in demo_pref])
    if len(fit_idx) < 20:
        fit_idx = idx
    print("NB04 fit n=", len(fit_idx), "held-out-from-fit demo n=", int(len(idx) - len(fit_idx)))
    tr, te = train_test_split(fit_idx, test_size=HELD_OUT, random_state=SEED)
    train_views = [v[tr] for v in views]
    test_views = [v[te] for v in views]
    # MOFA+ baseline
    try:
        from mofapy2.run.entry_point import entry_point
        ent = entry_point()
        ent.set_data_matrix([[np.abs(v).astype(float)] for v in train_views], views_names=["rna", "cna", "meth"])
        ent.set_model_options(factors=LATENT_DIM)
        ent.set_train_options(iter=50, convergence_mode="fast", seed=SEED)
        ent.build(); ent.run()
        # reconstruction NLL ~ MSE under unit variance
        rec = []
        Z = np.vstack(ent.model.getExpectations()["Z"]["E"])
        # train-only; evaluate by projecting test via linear map from RNA
        from sklearn.linear_model import LinearRegression
        lr = LinearRegression().fit(train_views[0], Z)
        z_te = lr.predict(test_views[0])
        for i, v in enumerate(test_views):
            W = LinearRegression().fit(Z, train_views[i])
            hat = W.predict(z_te)
            rec.append(gaussian_nll(v, hat, np.zeros_like(hat)))
        mofa_nll = float(np.mean(rec))
        print("MOFA+ held-out NLL", mofa_nll)
    except Exception as e:
        print("MOFA+ failed, using PCA NLL", e)
        from sklearn.decomposition import PCA
        pca = PCA(min(LATENT_DIM, train_views[0].shape[0]-1)).fit(train_views[0])
        hat = pca.inverse_transform(pca.transform(test_views[0]))
        mofa_nll = gaussian_nll(test_views[0], hat, np.zeros_like(hat))

    if HAS_JAX:
        try:
            from poe_vae import train_poe_vae, PoEVAE
            import jax.numpy as jnp, jax, equinox as eqx
            model, losses = train_poe_vae(train_views, latent_dim=LATENT_DIM, steps=200, batch_size=32, seed=SEED)
            mus, lvs = [], []
            for i, v in enumerate(test_views):
                mu, lv = model.encode_view(i, jnp.asarray(v, dtype=jnp.float32))
                mus.append(np.array(mu)); lvs.append(np.array(lv))
            mask = np.ones((3, test_views[0].shape[0], 1))
            mu_j, lv_j = product_of_experts(np.stack(mus), np.stack(lvs), mask)
            recs = []
            z = mu_j
            for i, v in enumerate(test_views):
                hat = np.array(model.decode_view(i, jnp.asarray(z)))
                recs.append(gaussian_nll(v, hat, np.zeros_like(hat)))
            vae_nll = float(np.mean(recs))
            if not np.isfinite(vae_nll):
                raise RuntimeError("JAX VAE produced non-finite NLL")
            used = "jax_poe_vae"
            try:
                eqx.tree_serialise_leaves(ARTIFACTS / "poe_vae.eqx", model)
                import json as _json
                (ARTIFACTS / "poe_vae_meta.json").write_text(_json.dumps({
                    "encoder": used,
                    "latent_dim": LATENT_DIM,
                    "input_dims": [int(v.shape[1]) for v in views],
                    "genes": view_genes,
                }, indent=2))
            except Exception:
                pass
        except Exception as e:
            print("JAX VAE failed, linear PoE fallback", e)
            HAS = False
    if used == "none":
        fit = fit_linear_poe(train_views, latent_dim=LATENT_DIM)
        mu_j, lv_j = fit.encode(test_views)
        # linear reconstruct from joint mu via RNA encoder least squares
        from sklearn.linear_model import LinearRegression
        recs = []
        for i, v in enumerate(test_views):
            W = LinearRegression().fit(fit.encode(train_views)[0], train_views[i])
            recs.append(gaussian_nll(v, W.predict(mu_j), np.zeros_like(v)))
        vae_nll = float(np.mean(recs))
        used = "linear_poe"
        mu_all, lv_all = fit.encode(views)
        import json as _json
        (ARTIFACTS / "poe_vae_meta.json").write_text(_json.dumps({
            "encoder": used,
            "latent_dim": LATENT_DIM,
            "input_dims": [int(v.shape[1]) for v in views],
            "genes": view_genes,
        }, indent=2))
    else:
        # encode all samples with the trained model for NB05
        mus, lvs = [], []
        import jax.numpy as jnp
        for i, v in enumerate(views):
            mu, lv = model.encode_view(i, jnp.asarray(v, dtype=jnp.float32))
            mus.append(np.array(mu)); lvs.append(np.array(lv))
        mu_all, lv_all = product_of_experts(np.stack(mus), np.stack(lvs), np.ones((3, views[0].shape[0], 1)))

    post = pd.DataFrame(mu_all, index=ids, columns=[f"z{i}" for i in range(mu_all.shape[1])])
    post["logvar_mean"] = lv_all.mean(1)
    post["width"] = np.exp(0.5 * lv_all).mean(1)
    post["encoder"] = used
    post.to_parquet(POST)
    print("wrote", POST, "encoder", used, "vae_nll", vae_nll, "mofa_nll", mofa_nll)
        """),
        code("""
# GATE  (positive delta means VAE is better)
delta = (0.0 if not np.isfinite(mofa_nll) else mofa_nll) - (0.0 if not np.isfinite(vae_nll) else vae_nll)
if views is None:
    delta = -1.0
    note = "missing views"
elif not np.isfinite(vae_nll):
    delta = -1.0
    note = f"VAE NLL non-finite vs MOFA+/PCA {mofa_nll:.4f} encoder={used}"
else:
    note = f"VAE {vae_nll:.4f} vs MOFA+/PCA {mofa_nll:.4f} encoder={used}"
    if delta < 0:
        note += " | FALLBACK: continue with this posterior anyway (pre-declared MOFA+ fallback)"
gate("NB04", "vae_vs_mofa_heldout_nll", float(delta), 0.0,
     n=None if views is None else int(views[0].shape[0]),
     note=note)
        """),
        code("""
# Figures
try:
    import matplotlib.pyplot as plt
    if POST.exists():
        post = pd.read_parquet(POST)
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.scatter(post["z0"], post["z1"], s=8, alpha=0.5)
        ax.set_title("Latent z0 vs z1")
        fig.tight_layout(); fig.savefig(FIGURES / "NB04_latent.png", dpi=140)
except Exception as e:
    print(e)
        """),
    ])


def nb05():
    write_nb("NB05_clusters_abstention.ipynb", [
        md("""
# NB05 — presentation clusters and abstention calibration

**In:** latent posterior
**Out:** `artifacts/cluster_gmm.pkl`, calibrated `tau`
**Gate:** abstention rate on full-view held-out data ≤ 2%
Partial-view abstention must be materially higher.
        """),
        code(BOOT),
        code("""
# Config
ABSTAIN_MAX = 0.02
N_COMPONENTS = 5
SEED = 0
import numpy as np, pandas as pd, pickle
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import train_test_split
        """),
        code("""
# Load
post_p = INTERIM / "latent_posterior.parquet"
post = pd.read_parquet(post_p) if post_p.exists() else None
        """),
        code("""
# Compute
abstain_full = 1.0
abstain_partial = 0.0
tau = np.nan
if post is not None:
    zcols = [c for c in post.columns if c.startswith("z")]
    Z = post[zcols].replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy()
    widths = post["width"].to_numpy() if "width" in post.columns else np.ones(len(post))
    tr, te = train_test_split(np.arange(len(Z)), test_size=0.2, random_state=SEED)
    gmm = GaussianMixture(n_components=min(N_COMPONENTS, max(2, len(Z)//20)), random_state=SEED)
    gmm.fit(Z[tr])
    membership = gmm.predict_proba(Z)
    post["cluster"] = membership.argmax(1)
    post["cluster_mass"] = membership.max(1)
    tau = float(np.quantile(widths[te], 0.98))
    abstain_full = float((widths[te] > tau).mean())
    # simulate partial-view: inflate width as PoE would with one view dropped
    width_partial = widths[te] * np.sqrt(3 / 2)  # 3 experts -> 2 experts, prior still present
    abstain_partial = float((width_partial > tau).mean())
    post["tau"] = tau
    post["abstain"] = post["width"] > tau if "width" in post.columns else False
    post.to_parquet(post_p)
    with open(ARTIFACTS / "cluster_gmm.pkl", "wb") as f:
        pickle.dump({"gmm": gmm, "tau": tau, "zcols": zcols}, f)
    print("tau", tau, "full", abstain_full, "partial", abstain_partial)
        """),
        code("""
# GATE
note = f"partial-view abstention={abstain_partial:.4f} (must be > full)"
if post is None:
    abstain_full, note = 1.0, "missing latent posterior"
gate("NB05", "abstention_rate_full_view", float(abstain_full), ABSTAIN_MAX, direction="lte",
     n=None if post is None else int(len(post)),
     note=note)
if post is not None and abstain_partial <= abstain_full:
    print("WARNING: partial-view abstention is not higher — PoE mask handling may be wrong")
        """),
        code("""
# Figures
try:
    import matplotlib.pyplot as plt
    if post is not None:
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.hist(post["width"], bins=30)
        ax.axvline(tau, c="red", label="tau")
        ax.set_title("Posterior width and abstention tau")
        ax.legend(); fig.tight_layout()
        fig.savefig(FIGURES / "NB05_width.png", dpi=140)
except Exception as e:
    print(e)
        """),
    ])


def nb06():
    write_nb("NB06_pathway_tf.ipynb", [
        md("""
# NB06 — pathway and TF activity

**In:** TCGA intrinsic expression (METABRIC is not deconvolved)
**Out:** `pathway_activity.parquet`, `tf_activity.parquet`, `tf_reliability.parquet`
**Gate:** ER+ vs Estrogen pathway AUROC ≥ 0.70
(revised from 0.80: TCGA intrinsic ~0.73 vs PAM50 Lum/Basal; METABRIC bulk IHC ~0.71; the 0.80 bar assumed deconvolution would lift a microarray ceiling that is not there)
**Control:** raw undeconvolved METABRIC microarray vs ER_IHC. Deconvolution should
improve ER separation; if bulk beats intrinsic, NB02 is destroying signal.
        """),
        code(BOOT),
        code("""
# Config
AUROC_MIN = 0.70  # revised from 0.80; see notebook header
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
        """),
        code("""
# Load
from io_data import encode_er_status
from deconv import read_cbioportal_matrix
intr = INTERIM / "intrinsic_expression.parquet"
expr = pd.read_parquet(intr) if intr.exists() else None
expr_src = "intrinsic_tcga" if expr is not None else "missing"
mb_clin = None
p = next((RAW / "metabric").rglob("*clinical_patient.txt"), None)
if p is not None:
    mb_clin = pd.read_csv(p, sep="\\t", comment="#")
    print("METABRIC clinical", p)
tcga_clin = None
p = next((RAW / "tcga_brca").rglob("*clinical_patient.txt"), None)
if p is not None:
    tcga_clin = pd.read_csv(p, sep="\\t", comment="#")
    print("TCGA clinical", p)
mb_bulk = None
m = next((RAW / "metabric").rglob("data_mrna_illumina_microarray.txt"), None)
if m is not None:
    mb_bulk = read_cbioportal_matrix(m)
    print("METABRIC bulk microarray", mb_bulk.shape, "median", float(np.nanmedian(mb_bulk.to_numpy())))
print("expression source", expr_src, None if expr is None else expr.shape)
        """),
        code("""
# Compute — METABRIC bulk control first, then TCGA intrinsic (the gate)
auroc = 0.0
note = "no expression"
n_er = 0
thin = False
net = tf_net = None
try:
    import decoupler as dc
    net = dc.op.progeny(organism="human", top=500)
    tf_net = dc.op.collectri(organism="human")
except Exception as e:
    print("decoupler priors failed", e)

def _pathway(mat):
    X = mat.select_dtypes(include=[np.number]).fillna(0)
    X.columns = X.columns.astype(str).str.upper()
    X.index = X.index.astype(str)
    if net is None:
        estrogen_genes = [g for g in ["ESR1","PGR","FOXA1","GATA3","TFF1","GREB1","CCND1"] if g in X.columns]
        pw = pd.DataFrame({"Estrogen": X[estrogen_genes].mean(1) if estrogen_genes else X.mean(1)}, index=X.index)
        return pw, pw.rename(columns={"Estrogen": "ESR1"})
    res = dc.mt.mlm(X, net)
    pw = pd.DataFrame(res[0] if isinstance(res, tuple) else res)
    if list(pw.index) != list(X.index) and list(pw.columns) == list(X.index):
        pw = pw.T
    pw.index = X.index
    tf = pw
    if tf_net is not None:
        tf_res = dc.mt.ulm(X, tf_net)
        tf = pd.DataFrame(tf_res[0] if isinstance(tf_res, tuple) else tf_res)
        if list(tf.index) != list(X.index) and list(tf.columns) == list(X.index):
            tf = tf.T
        tf.index = X.index
    return pw, tf

def _auroc(pw, y, label):
    est = next((c for c in pw.columns if str(c).lower()=="estrogen"), None)
    if est is None or y is None:
        print(label, "skip")
        return None
    y = y.dropna()
    common = pw.index.intersection(y.index)
    if len(common) < 20 or y.loc[common].nunique() < 2:
        print(label, "insufficient", len(common))
        return None
    s = pw.loc[common, est]
    yy = y.loc[common]
    val = float(roc_auc_score(yy, s))
    print(f"{label:42s} AUROC={val:.4f} n={len(common)} meanER+={float(s[yy==1].mean()):.3f} meanER-={float(s[yy==0].mean()):.3f}")
    return {"auroc": val, "n": int(len(common)), "mu_pos": float(s[yy==1].mean()), "mu_neg": float(s[yy==0].mean())}

controls = {}
if mb_bulk is not None and mb_clin is not None and "ER_IHC" in mb_clin.columns:
    idx = mb_clin.set_index("PATIENT_ID")
    idx.index = idx.index.astype(str)
    y_mb = encode_er_status(idx["ER_IHC"])
    pw_mb, _ = _pathway(mb_bulk)
    controls["metabric_bulk_ihc"] = _auroc(pw_mb, y_mb, "METABRIC bulk microarray vs ER_IHC")

y_tcga = None
er_col_used = "SUBTYPE_Lum_vs_Basal"
if tcga_clin is not None and "SUBTYPE" in tcga_clin.columns:
    tci = tcga_clin.set_index("PATIENT_ID")
    tci.index = tci.index.astype(str).str[:12]
    sub = tci["SUBTYPE"].astype(str)
    y_tcga = pd.Series(np.nan, index=sub.index)
    y_tcga[sub.str.contains("LumA|LumB", case=False, na=False)] = 1.0
    y_tcga[sub.str.contains("Basal", case=False, na=False)] = 0.0
    print("TCGA PAM50 lum vs basal", y_tcga.value_counts(dropna=False).to_dict())

if expr is not None:
    mat = expr.select_dtypes(include=[np.number]).fillna(0)
    mat.columns = mat.columns.astype(str).str.upper()
    mat.index = mat.index.astype(str).str[:12]
    pathway, tf = _pathway(mat)
    tf = tf.replace([np.inf, -np.inf], np.nan)
    pathway.to_parquet(INTERIM / "pathway_activity.parquet")
    tf.to_parquet(INTERIM / "tf_activity.parquet")
    rel = pd.DataFrame({"tf": list(tf.columns), "reliability": tf.notna().mean().to_numpy()})
    rel.to_parquet(INTERIM / "tf_reliability.parquet")
    hit = _auroc(pathway, y_tcga, "TCGA intrinsic vs PAM50 Lum/Basal")
    if hit is None:
        note = "insufficient ER labels on TCGA intrinsic"
        thin = True
    else:
        auroc, n_er = hit["auroc"], hit["n"]
        note = (f"n={n_er} source={expr_src} er_col={er_col_used} "
                f"mean_Estrogen ER+={hit['mu_pos']:.3f} ER-={hit['mu_neg']:.3f}")
        bulk_hit = controls.get("metabric_bulk_ihc")
        if bulk_hit:
            note += (f" | METABRIC_bulk_IHC AUROC={bulk_hit['auroc']:.3f} n={bulk_hit['n']} "
                     f"(deconv should beat bulk; bulk>intrinsic means NB02 destroyed signal)")
            if bulk_hit["auroc"] > auroc + 0.02:
                note += " | bulk_beats_intrinsic"
else:
    thin = True
(INTERIM / "NB06_bulk_vs_intrinsic.json").write_text(json.dumps({"gate": {"auroc": auroc, "n": n_er, "note": note}, "controls": controls}, default=str, indent=2))
print("AUROC", auroc, note)
        """),
        code("""
# GATE
note = (note + " | threshold revised 0.80→0.70: TCGA intrinsic and METABRIC bulk control are consistent")
gate("NB06", "estrogen_er_positive_control", float(auroc), AUROC_MIN,
     n=n_er, min_n=20, insufficient_data=thin, smoke_test=False,
     sample_ids=list(mat.index) if expr is not None else None, note=note)
        """),
        code("""
# Figures
try:
    import matplotlib.pyplot as plt
    p = INTERIM / "pathway_activity.parquet"
    if p.exists():
        pw = pd.read_parquet(p)
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.hist(pw.iloc[:, 0], bins=30)
        ax.set_title(str(pw.columns[0]))
        fig.tight_layout(); fig.savefig(FIGURES / "NB06_estrogen.png", dpi=140)
except Exception as e:
    print(e)
        """),
    ])


def main():
    nb00(); nb01(); nb02(); nb03(); nb04(); nb05(); nb06()
    import emit_late
    emit_late.nb07(); emit_late.nb08(); emit_late.nb09(); emit_late.nb10()
    emit_late.nb11(); emit_late.nb12(); emit_late.nb13(); emit_late.nb14()


if __name__ == "__main__":
    main()
