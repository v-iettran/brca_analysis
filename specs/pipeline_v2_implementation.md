# Pipeline v2 — implementation spec (notebook-first)

**Companion to:** `pipeline_v2_spec.md` (the design document)
**This document:** how to actually build it, notebook by notebook, before any app code is written
**Repo:** `Lifework-Health/person_med_a2`

---

## 0. Working method

### 0.1 The rule

**No code enters `application/` until the notebook that produced it has passed its gate.**

Each notebook ends with an explicit pass/fail check. A failed gate means you stop, not that you
proceed with a caveat. The gates exist because this pipeline has several stages that will produce
plausible-looking output while being silently wrong — cross-platform harmonisation and ODE
parameter fitting especially.

### 0.2 Notebook contract

Every notebook follows the same shape:

```
1. Header cell     — purpose, inputs, outputs, gate, expected runtime
2. Config cell     — all paths and constants, no magic numbers below this cell
3. Load            — read from data/interim/, never recompute upstream
4. Compute
5. Persist         — write to data/interim/ or artifacts/v2/ as parquet
6. GATE cell       — assert-based, prints PASS/FAIL, writes to gates.jsonl
7. Figures         — for the writeup, saved to reports/v2/figures/
```

Notebooks communicate **only through files on disk**. No notebook imports another. This is
deliberate: it means any notebook can be re-run in isolation, and the moment a stage is stable
you lift its compute cell into a module without untangling dependencies.

### 0.3 Directory layout to create

```
person_med_a2/
├── notebooks/v2/           # NB00 … NB14
├── data/
│   ├── raw/                # downloaded, never modified, gitignored
│   ├── interim/            # notebook-to-notebook handoff, parquet, gitignored
│   └── reference/          # small curated files, COMMITTED (node lists, drug tables)
├── artifacts/v2/           # promotable outputs (models, fitted params)
├── reports/v2/
│   ├── figures/
│   └── gates.jsonl         # append-only gate log, COMMITTED
└── src/pipeline_core_v2/   # promotion target — empty until Phase 1 passes
```

Add to `.gitignore`: `data/raw/`, `data/interim/`, `artifacts/v2/*.pt`, `artifacts/v2/*.eqx`.

Commit `data/reference/` and `reports/v2/gates.jsonl` — the gate log is the audit trail that
makes the eventual writeup defensible.

### 0.4 Gate logging

Put this in `notebooks/v2/_gate.py` and import it in every notebook:

```python
import json, datetime, pathlib

GATES = pathlib.Path("reports/v2/gates.jsonl")

def gate(notebook: str, name: str, value: float, threshold: float,
         direction: str = "gte", note: str = "") -> bool:
    passed = value >= threshold if direction == "gte" else value <= threshold
    rec = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notebook": notebook, "gate": name,
        "value": float(value), "threshold": float(threshold),
        "direction": direction, "passed": bool(passed), "note": note,
    }
    GATES.parent.mkdir(parents=True, exist_ok=True)
    with GATES.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(f"{'PASS' if passed else 'FAIL'}  {name}: {value:.4f} "
          f"({'≥' if direction == 'gte' else '≤'} {threshold})")
    if note:
        print(f"      {note}")
    return passed
```

---

## 1. Environment

Two environments. R is unavoidable — CARNIVAL, decoupleR's reference implementation, and
BayesPrism are all R-native, and reimplementing them is not a good use of your time.

### 1.1 Python

`env/v2_requirements.txt`:

```
# existing
pandas>=2.3
numpy>=2.0
scipy>=1.14
scikit-learn>=1.5
matplotlib>=3.9
seaborn>=0.13
pyarrow>=17

# v2 additions
jax[cpu]>=0.4.35          # cuda12 variant if you have a GPU
equinox>=0.11             # VAE + ODE parameterisation
diffrax>=0.6              # differentiable ODE solver
optax>=0.2                # optimiser
jaxopt>=0.8               # bounded optimisation for ODE fitting
torch>=2.4                # fallback for the VAE if JAX proves painful
decoupler>=1.8            # Python port of decoupleR — PROGENy + CollecTRI
omnipath>=1.0             # OmniPath Python client
mudata>=0.3               # multi-view container
mofapy2>=0.7              # MOFA+ baseline for the VAE comparison
mapie>=0.9                # conformal prediction
lifelines>=0.29           # survival validation
tqdm
jupyterlab
```

Install: `pip install -r env/v2_requirements.txt --break-system-packages`

### 1.2 R

`env/v2_setup.R`:

```r
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
BiocManager::install(c("CARNIVAL", "decoupleR", "OmnipathR", "limma", "sva"))
install.packages(c("devtools", "data.table", "arrow"))
devtools::install_github("Danko-Lab/BayesPrism/BayesPrism")
# ILP solver: CBC is free. CPLEX is faster; free via IBM Academic Initiative.
# install.packages("lpSolve")  # will NOT scale to genome-wide PKN — CBC minimum
```

**Handoff between languages is parquet via `arrow`**, both directions. No CSV — you will lose
float precision on activity scores and it will show up as irreproducible CARNIVAL solutions.

### 1.3 Compute budget

| Stage | Cost | Where |
|---|---|---|
| Harmonisation | minutes | laptop |
| BayesPrism | 2–6 h for ~2,000 samples | needs ~32 GB RAM; consider a VPS |
| PoE-VAE training | 20–60 min CPU, <10 min GPU | laptop OK |
| CARNIVAL | ~30–90 s per patient × n | embarrassingly parallel; VPS |
| ODE fitting | hours; the main cost | GPU strongly preferred |
| Conformal | minutes | laptop |

You already ran the VN30 autoresearch system overnight on a VPS — same pattern applies to
BayesPrism and the ODE fit. Everything else is laptop-scale.

---

## 2. Data acquisition (NB00)

### 2.1 Manifest

Create `data/reference/v2_source_manifest.csv` mirroring the existing `q2_source_manifest.csv`
convention — one row per source with URL, sha256, size, licence, retrieval date.

| Source | What | Size | Access |
|---|---|---|---|
| cBioPortal `brca_metabric` | Expression, CNA, clinical | ~400 MB | Direct download |
| TCGA-BRCA | RNA-seq (STAR counts), CNA, methylation 450k, clinical | ~3 GB | GDC portal / `TCGAbiolinks` |
| GTEx v8 breast | Normal reference | ~200 MB | GTEx portal |
| Wu et al. breast scRNA atlas | BayesPrism reference | ~2 GB | GEO GSE176078 |
| CPTAC-BRCA | Proteomics, for the S4 sanity check | ~500 MB | CPTAC DCC / `cptac` PyPI |
| GDSC2 | Dose-response (IC50 + raw curves) | ~150 MB | cancerrxgene.org |
| DepMap 24Q2 | CRISPR gene effect, expression, model metadata | ~1.5 GB | depmap.org |
| NCI-ALMANAC | Combination ComboScores | ~200 MB | Already in repo pipeline |
| OmniPath | Prior knowledge network | ~50 MB | API via `omnipath` / `OmnipathR` |
| SCAN-B | RNA-seq + treatment + outcome | ~2 GB | GEO GSE96058 — **apply early**, access can take weeks |

**Start the SCAN-B request on day one.** It's the best validation asset in the list and the only
one with a lead time.

### 2.2 NB00 — acquisition and integrity

**Purpose:** download everything, verify hashes, produce a single availability report.
**Gate:** all required sources present and hash-verified.

```python
# NB00 gate
required = ["metabric", "tcga_brca", "gtex_breast", "omnipath",
            "gdsc2", "depmap", "wu_scrna"]
missing = [s for s in required if not manifest.loc[s, "verified"]]
gate("NB00", "sources_available", len(missing), 0, direction="lte",
     note=f"missing: {missing}" if missing else "all present")
```

SCAN-B and CPTAC are *not* in `required` — they gate later notebooks (NB08, NB13), not this one.

---

## 3. Phase 1 — correctness fixes (NB01–NB03)

This phase improves the existing pipeline without any new modelling. It is the highest
value-per-risk work in the plan and it pays off measurably against the committed `outputs/q5/`
tables.

### 3.1 NB01 — cross-platform harmonisation

**In:** raw METABRIC expression, TCGA-BRCA STAR counts
**Out:** `data/interim/harmonised_expression.parquet`
**Gate:** PAM50 concordance ≥ 0.85
**Runtime:** ~15 min

Implement the rank-based default from design spec §3.1:

```python
from scipy.stats import rankdata
from scipy.special import ndtri

def inverse_normal_transform(X):
    """Per-sample within-gene-set rank → normal score.
    X: samples × genes. Kills platform scale, keeps within-patient ordering."""
    n = X.shape[1]
    R = np.apply_along_axis(rankdata, 1, X)
    return ndtri((R - 0.5) / n)
```

Restrict to the intersection of genes present in both platforms *before* transforming — the rank
denominator must be the same gene set or the scores aren't comparable.

**The gate.** Train a PAM50 classifier on transformed METABRIC using the published METABRIC
PAM50 calls; predict on transformed TCGA; compare to published TCGA PAM50 calls.

```python
concordance = (pred_tcga_pam50 == published_tcga_pam50).mean()
gate("NB01", "pam50_concordance", concordance, 0.85)
```

Also compute and log balanced accuracy — overall concordance can be inflated by the Luminal A
majority class.

**If it fails:** try cohort-specific z-scoring (option 2 in the design spec) before reaching for
ComBat. If you do use ComBat, protect subtype + purity + stage in the model matrix and report
pre/post subtype separation in the same notebook. Do not pool raw values under any circumstance.

**Deliverable figure:** UMAP of both cohorts pre- and post-harmonisation, coloured by cohort and
by PAM50. Cohort separation should collapse; subtype separation should survive. If both collapse,
you've over-corrected.

### 3.2 NB02 — deconvolution

**In:** harmonised expression, Wu et al. scRNA reference
**Out:** `data/interim/deconvolution_posterior.parquet`, `data/interim/intrinsic_expression.parquet`
**Gate:** purity Spearman ≥ 0.7 against CNA-derived purity
**Runtime:** 2–6 h (R)

R script called from the notebook via `subprocess`, or run the notebook in an R kernel. Key
BayesPrism configuration:

```r
prism <- new.prism(
  reference   = sc_ref_counts,       # raw counts, NOT normalised
  mixture     = bulk_counts,
  input.type  = "count.matrix",
  cell.type.labels = ct_labels,      # major lineages
  cell.state.labels = cs_labels,     # malignant subclusters
  key = "malignant",                 # marks the tumour compartment
  outlier.cut = 0.01, outlier.fraction = 0.1
)
res <- run.prism(prism = prism, n.cores = 8)
theta <- get.fraction(res, which.theta = "final", state.or.type = "type")
Z_mal <- get.exp(res, state.or.type = "type", cell.name = "malignant")
```

Per the BayesPrism documentation, exclude ribosomal, mitochondrial, and sex-chromosome genes via
`cleanup.genes()` — these carry platform batch effects that BayesPrism cannot correct.

**The gate.** You have two independent purity estimates: BayesPrism's malignant fraction, and
CNA-derived purity (ASCAT/ABSOLUTE, or the TCGA published purity calls). They should agree.

```python
rho = spearmanr(bayesprism_malignant_frac, cna_purity).statistic
gate("NB02", "purity_concordance", rho, 0.7)
```

**Watch for the known failure mode.** Tran et al. 2023 found that in breast specifically, most
methods mis-assign normal epithelium as cancer epithelium as purity rises, and that the error is
subtype-dependent. Stratify the concordance by PAM50 and log it per subtype. A global pass with a
subtype-specific failure is worse than an honest global fail, because it will bias the drug
ranking in a subtype-dependent direction — exactly the bias v1 has undeclared.

**Optional but recommended:** run DWLS on the same inputs as a concordance check. Cheap, and Tran
et al. rank it alongside BayesPrism.

### 3.3 NB03 — normal reference and the reversal target

**In:** GTEx breast, TCGA adjacent normals, deconvolved intrinsic expression
**Out:** `data/interim/normal_reference.parquet`
**Gate:** no formal threshold — this notebook produces a diagnostic, not a model
**Runtime:** ~30 min

Build the normal-breast manifold that gives the reversal objective a fixed point
(design spec §3.3).

Deconvolve GTEx breast the same way, and compare **epithelial compartment to epithelial
compartment**. GTEx breast is adipose-dominant post-mortem tissue; the raw bulk profile is not a
usable epithelial reference and using it as one is a real error.

**Diagnostic to produce:** for each METABRIC cluster, compute the distance from cluster centroid
to (a) the other clusters' centroids and (b) the normal epithelial centroid. If those two
directions are near-orthogonal, you have direct quantitative evidence for the `LIMITATIONS.md` §9
claim — "reversing away from cluster k" and "moving toward normal" are different objectives. That
figure belongs in the paper.

### 3.4 Phase 1 checkpoint

Before proceeding: re-run the existing Q2 projection on deconvolved intrinsic expression instead
of bulk, and compare the drug ranking to the committed `outputs/q5/tables/`. Report rank
correlation. If the ranking barely moves, deconvolution wasn't the problem you thought it was and
you should say so. If it moves a lot, you have a concrete result: *the v1 ranking was substantially
driven by microenvironment composition.*

Either outcome is publishable and both are worth knowing before you build four more stages.

---

## 4. Phase 2 — the latent model (NB04–NB05)

### 4.1 NB04 — product-of-experts VAE

**In:** harmonised intrinsic expression, CNA segments, methylation β
**Out:** `artifacts/v2/poe_vae.eqx`, `data/interim/latent_posterior.parquet`
**Gate:** held-out negative log-likelihood below MOFA+ on the same split
**Runtime:** 20–60 min

The PoE combination is the whole trick, and it's about eight lines:

```python
import jax.numpy as jnp

def product_of_experts(mus, logvars, mask):
    """mus, logvars: (n_views, batch, latent_dim)
       mask: (n_views, batch, 1) — 1 if view present
       Prior N(0, I) is included as an always-present expert."""
    precisions = jnp.exp(-logvars) * mask          # zero out absent views
    prior_prec = jnp.ones_like(precisions[0])       # prior precision = 1
    total_prec = precisions.sum(axis=0) + prior_prec
    weighted_mu = (mus * precisions).sum(axis=0)    # prior mean 0 contributes nothing
    mu_joint = weighted_mu / total_prec
    logvar_joint = -jnp.log(total_prec)
    return mu_joint, logvar_joint
```

Absent view → its precision term is zeroed → it drops out of both sums → the posterior widens
automatically. That is the entire mechanism that replaces the surrogate classifier and the three
abstention thresholds.

**Sub-sampled training (Wu & Goodman).** Each batch must include full-view examples *and*
randomly-masked subsets, so the unimodal encoders learn to stand alone:

```python
def sample_view_mask(key, n_views, batch):
    full = jnp.ones((n_views, batch, 1))
    rand = jax.random.bernoulli(key, 0.5, (n_views, batch, 1)).astype(float)
    # guarantee at least one view present per sample
    rand = jnp.where(rand.sum(0, keepdims=True) == 0, full, rand)
    return jnp.concatenate([full, rand], axis=1)  # both in the same update
```

**Decoder likelihoods** — get these right, they matter more than architecture:
RNA (rank-normal) → Gaussian; CNA (log-ratio) → Gaussian; methylation (β ∈ [0,1]) → Beta.
Using Gaussian for β-values will produce out-of-range reconstructions and a quietly wrong ELBO.

**Platform adversary.** Small head predicting cohort from `z`, with gradient reversal. Target:
adversary accuracy near chance. Log it — if the adversary can identify cohort from the latent,
your downstream results are partly platform artefacts.

**The gate:**

```python
gate("NB04", "vae_vs_mofa_heldout_nll", mofa_nll - vae_nll, 0.0,
     note=f"VAE {vae_nll:.2f} vs MOFA+ {mofa_nll:.2f}")
```

**If it fails:** fall back to MOFA+ (which also handles missing views) and say so in the writeup.
This is a pre-declared fallback, not a failure of the project — the PoE-VAE is a bet on nonlinear
methylation–expression coupling being worth the interpretability cost, and that bet can lose.

### 4.2 NB05 — presentation clusters and abstention calibration

**In:** latent posterior
**Out:** `artifacts/v2/cluster_gmm.pkl`, calibrated thresholds
**Gate:** abstention rate on full-view held-out data < 2%
**Runtime:** ~10 min

Fit a Gaussian mixture on latent means for the **presentation layer only**. Cluster membership is
posterior mass under the mixture — a real probability, not a classifier softmax.

Calibrate the abstention threshold on posterior width:

```python
widths = np.exp(0.5 * logvar_joint).mean(axis=1)   # mean posterior sd
tau = np.quantile(widths[full_view_heldout], 0.98)
abstain_rate = (widths[full_view_heldout] > tau).mean()
gate("NB05", "abstention_rate_full_view", abstain_rate, 0.02, direction="lte")
```

Then check the thing that actually matters: the abstention rate on *partial-view* patients should
be materially higher. If it isn't, the PoE isn't propagating uncertainty and something is wrong
with the mask handling in NB04.

**Deletion list for the app** (do this now, in a branch, so Phase 2 lands cleanly):

| Delete | Replace with |
|---|---|
| `pipeline_core/cluster_model.py` | latent posterior |
| `MIN_GENE_COVERAGE` | per-gene encoder masking |
| `LOW_CONFIDENCE_THRESHOLD` | posterior entropy |
| `ABSTENTION_THRESHOLD` | calibrated `tau` |
| `jobs/train_cluster_classifier.py` | `jobs/train_poe_vae.py` |

---

## 5. Phase 3 — causal layer (NB06–NB08)

### 5.1 NB06 — pathway and TF activity

**In:** intrinsic expression
**Out:** `data/interim/pathway_activity.parquet`, `data/interim/tf_activity.parquet`
**Gate:** ER-positive samples show elevated Estrogen pathway activity (sanity, AUROC ≥ 0.8)
**Runtime:** ~20 min

`decoupler` in Python handles both:

```python
import decoupler as dc

progeny = dc.get_progeny(organism="human", top=500)
collectri = dc.get_collectri(organism="human", split_complexes=False)

dc.run_mlm(mat=expr, net=progeny, source="source", target="target",
           weight="weight", verbose=True)
pathway_acts = expr.obsm["mlm_estimate"]

dc.run_ulm(mat=expr, net=collectri, source="source", target="target",
           weight="weight", verbose=True)
tf_acts = expr.obsm["ulm_estimate"]
```

Run the consensus of several methods (`mlm`, `ulm`, `wsum`, `aREA`) rather than betting on one —
`dc.decouple()` does this and reports agreement.

**The gate is a positive control.** ER status is known for every METABRIC patient. PROGENy
Estrogen activity must separate ER+ from ER−. If it doesn't, something upstream (harmonisation,
deconvolution, gene ID mapping) is broken, and this catches it cheaply before CARNIVAL.

```python
auroc = roc_auc_score(er_status, pathway_acts["Estrogen"])
gate("NB06", "estrogen_er_positive_control", auroc, 0.8)
```

Add a second control: PROGENy Hypoxia should correlate with a hypoxia gene signature score.

**Methylation gating.** For each TF, compute mean promoter methylation across its CollecTRI
regulon targets. High methylation → flag that TF's activity estimate as low-reliability. Persist
as `tf_reliability.parquet`. This is where methylation earns its place (design spec §5.5) and it
is a genuinely novel touch worth writing up.

### 5.2 NB07 — CARNIVAL causal networks

**In:** TF activity, pathway activity, CNA, OmniPath PKN
**Out:** `data/interim/causal_networks/{sample_id}.json`
**Gate:** inferred-active nodes vs DepMap CRISPR essentiality, AUROC ≥ 0.65
**Runtime:** 30–90 s per sample; parallelise

R, because CARNIVAL is R:

```r
library(CARNIVAL); library(OmnipathR)

pkn <- import_omnipath_interactions() |>
  dplyr::filter(consensus_direction == 1, (is_stimulation + is_inhibition) == 1) |>
  dplyr::transmute(source = source_genesymbol,
                   interaction = ifelse(is_stimulation == 1, 1, -1),
                   target = target_genesymbol)

res <- runCARNIVAL(
  inputObj    = perturbation,   # NULL → InvCARNIVAL; set for StdCARNIVAL
  measObj     = tf_activity_row,
  netObj      = pkn,
  weightObj   = pathway_activity_row,
  solver      = "cbc",
  timelimit   = 300
)
```

**Mode selection:** StdCARNIVAL when a driver is known from CNA/mutation — pass it as `inputObj`
with its sign constrained. InvCARNIVAL otherwise. Log which mode ran per sample.

**CNA dosage prior:** amplified genes get their node's activation cost reduced in the objective;
deleted genes get inhibition favoured. This is where CNA enters as a *constraint on inference*
rather than another feature block.

**The gate.** DepMap gives CRISPR gene effect scores per cell line. For cell lines you can match
to CARNIVAL-inferred networks, nodes inferred active should be enriched for essentiality:

```python
auroc = roc_auc_score(is_essential, inferred_active_score)
gate("NB07", "carnival_vs_depmap_essentiality", auroc, 0.65)
```

This is the first genuinely independent validation in the pipeline — DepMap knockouts are a
different assay from anything upstream.

**Practical warnings:** lpSolve will not finish on a genome-wide PKN; use CBC minimum, CPLEX if
you can get the academic licence. Set `timelimit` and record which samples hit it — a
time-limited solution is a feasible-but-not-optimal network and should be flagged, not silently
used.

### 5.3 NB08 — CPTAC protein sanity check

**In:** intrinsic expression, CPTAC-BRCA proteomics
**Out:** `data/reference/node_reliability.csv`
**Gate:** ≥60% of planned ODE nodes show RNA↔protein Spearman ≥ 0.3
**Runtime:** ~30 min

**This gate decides whether Phase 4 happens.**

The logic-ODE personalises node abundance from mRNA. If mRNA doesn't track protein for the nodes
in scope, the personalisation is fiction. Test it before spending eight weeks.

```python
rhos = {g: spearmanr(rna[g], protein[g]).statistic
        for g in ODE_NODE_GENES if g in protein.columns}
frac_ok = np.mean([r >= 0.3 for r in rhos.values()])
gate("NB08", "rna_protein_concordance", frac_ok, 0.6,
     note=f"n_nodes={len(rhos)}, median rho={np.median(list(rhos.values())):.3f}")
```

Persist the per-node ρ. Nodes below 0.3 get **wider priors** in the ODE fit rather than exclusion
— dropping them would change the topology, which you've committed to fixing from OmniPath.

**If this fails:** Phase 4 is not viable in its current form. Options in order of preference:
(a) narrow the node set to well-correlated genes only; (b) use phospho-proteomics from CPTAC to
personalise activity rather than abundance; (c) cut S4 and stop at Phase 3 + Phase 5, which is
still a complete and defensible pipeline.

---

## 6. Phase 4 — the ODE (NB09–NB11)

Highest risk. Do not start until NB08 passes.

### 6.1 NB09 — model construction and identifiability

**In:** OmniPath PKN, node list
**Out:** `data/reference/ode_topology.json`, identifiability report
**Gate:** all fitted parameters structurally identifiable (or fixed to priors)
**Runtime:** ~2 h including analysis

**Scope discipline: 20 nodes, CDK4/6–RB–E2F only.** Do not start at 60. Suggested node set:

```
Receptor/upstream : ESR1, ERBB2, EGFR, IGF1R
PI3K axis         : PIK3CA, AKT1, MTOR, PTEN
MAPK axis         : KRAS, BRAF, MAP2K1, MAPK1
Cell cycle core   : CCND1, CDK4, CDK6, CDKN2A, RB1, E2F1
Readout           : MKI67 (proliferation), CDKN1A (arrest)
```

Extract induced subgraph from OmniPath, keeping only signed consensus-direction edges. Persist
the topology as JSON — **committed to the repo**, because it's the structural prior and every
result depends on it.

The normalised-Hill form (Wittmann et al. 2009, HillCube):

```python
import diffrax, equinox as eqx, jax.numpy as jnp

def hill(x, k, n=2.0):
    """Normalised Hill: hill(0)=0, hill(1)=1, monotone increasing."""
    num = (x ** n) * (1.0 + k ** n)
    den = (x ** n) + (k ** n)
    return num / den

def make_rhs(topology, params):
    def rhs(t, x, args):
        drug_mult = args["drug_mult"]              # per-node inhibition factor
        B = boolean_interpolate(x, topology, params.k)   # HillCube of the logic rule
        return params.tau * (B * drug_mult - x)
    return rhs
```

**Identifiability, before any fitting:**

1. Fix `n = 2` for all Hill terms. Only `k` and `tau` are fitted.
2. Run `StructuralIdentifiability.jl` on the reduced system. Any structurally
   non-identifiable parameter gets **fixed to a literature prior**, not fitted.
3. Log the identifiable/fixed split. This report is a required part of the writeup.

```python
n_nonident = len(nonidentifiable_params)
gate("NB09", "structural_identifiability", n_nonident, 0, direction="lte",
     note=f"fixed to priors: {nonidentifiable_params}")
```

### 6.2 NB10 — fitting on GDSC

**In:** topology, DepMap cell-line expression, GDSC2 dose-response
**Out:** `artifacts/v2/ode_params.eqx`, profile likelihood report
**Gate:** predicted vs observed IC50 Spearman ≥ 0.4 on held-out drugs
**Runtime:** hours; GPU strongly preferred

**The central design decision: edge parameters are global, node abundances are per-line.**

```
Fitted once, shared across all cell lines : k (per edge), tau (per node)
Varies per cell line                      : x0 (initial state), node scaling
```

This turns hundreds of per-sample parameters into hundreds of parameters constrained by ~1,000
cell lines. It is what makes the fit identifiable, and it's the single most important line in
this notebook.

Drug action via Hill inhibition at achievable concentration:

```python
def drug_multiplier(target_idx, conc, ic50, h=1.0, n_nodes=20):
    m = jnp.ones(n_nodes)
    return m.at[target_idx].set(1.0 / (1.0 + (conc / ic50) ** h))
```

Bound `conc` by published plasma **Cmax** — build `data/reference/drug_pk.csv` with
`drug, target_gene, ic50_nm, cmax_nm, source_doi`. Curate by hand for the ~10 drugs in the
CDK4/6 scope; this is a half-day of work and it's what gives you the dose realism v1 cannot express.

Fit by backpropagating through `diffrax` with `optax`. Loss: MSE between predicted proliferation
index at 72 h and observed GDSC viability, across the dose series.

**Two gates:**

```python
gate("NB10", "gdsc_ic50_spearman", rho_heldout, 0.4)

n_unbounded = sum(1 for p in profiles if p.upper_ci is None)
gate("NB10", "profile_likelihood_bounded", n_unbounded, 0, direction="lte")
```

Profile likelihoods are not optional. A parameter with an unbounded profile means the data does
not constrain it, and any prediction that depends on it must be suppressed downstream — not
reported with a caveat.

**Held out properly:** hold out *drugs*, not observations. Random observation splits leak, because
the same drug appears in train and test at different doses.

### 6.3 NB11 — synergy and the falsification test

**In:** fitted ODE, ALMANAC ComboScores
**Out:** `data/interim/predicted_synergy.parquet`
**Gate:** predicted vs observed synergy Spearman ≥ 0.3 on held-out pairs
**Runtime:** ~2 h

**This is the load-bearing test of the entire v2 thesis.**

```python
def bliss_excess(model, params, x0, drug_a, drug_b, conc_a, conc_b):
    e_a  = 1 - simulate(model, params, x0, {drug_a: conc_a})
    e_b  = 1 - simulate(model, params, x0, {drug_b: conc_b})
    e_ab = 1 - simulate(model, params, x0, {drug_a: conc_a, drug_b: conc_b})
    return e_ab - (e_a + e_b - e_a * e_b)
```

Predict for every pair in the node set, then compare against ALMANAC on pairs the model never
saw. This inverts Q5's `0.35 × ComboScore` term: ALMANAC stops being an input weight and becomes
an independent validation target.

```python
gate("NB11", "synergy_vs_almanac_heldout", rho, 0.3,
     note=f"n_pairs={n}, n_breast_lines={k}")
```

**If this fails, the ODE is not earning its complexity.** Cut back to a narrower validated scope
or drop S4. That is a legitimate outcome and it is publishable: *"mechanistic simulation does not
outperform connectivity mapping for breast cancer drug prioritisation"* is a real finding given a
fair implementation. Write it up either way.

**The resistance output.** Simulate forward with feedback enabled, detect rebound:

```python
traj = simulate_trajectory(model, params, x0, drug, t_span=(0, 168))  # hours
rebound_nodes = [n for n in nodes
                 if traj[n, -1] > traj[n, :].min() * 1.5
                 and traj[n, -1] > traj[n, 0] * 1.2]
```

This produces the sentence no v1 component can: *"predicted response ~8 weeks, then IGF1R
compensation; consider adding an IGF1R inhibitor."* Validate the mechanism qualitatively against
literature for the known cases (PI3Ki → RTK feedback → MAPK rebound is well documented) before
trusting novel ones.

---

## 7. Phase 5 — transfer and calibration (NB12–NB13)

### 7.1 NB12 — PRECISE domain adaptation

**In:** DepMap cell-line expression, harmonised tumour expression
**Out:** `artifacts/v2/precise_projection.npz`
**Gate:** report transfer gain vs no adaptation (no fixed threshold)
**Runtime:** ~20 min

```python
def precise(X_source, X_target, n_pc=70, n_pv=40):
    Ps = PCA(n_pc).fit(X_source).components_
    Pt = PCA(n_pc).fit(X_target).components_
    U, s, Vt = np.linalg.svd(Ps @ Pt.T)
    pv_source = U.T @ Ps
    pv_target = Vt  @ Pt
    angles = np.arccos(np.clip(s, -1, 1))
    return pv_source[:n_pv], pv_target[:n_pv], angles
```

Principal vectors with small angles are directions shared by cell lines and tumours; large angles
are culture artefacts or microenvironment. Fit the response model in the aligned subspace only.

**Report both deltas separately** — the gain from deconvolution (NB02) and the gain from PRECISE.
They partially overlap, since deconvolution already removes microenvironment variance, and
conflating them would overstate either.

### 7.2 NB13 — conformal fusion

**In:** all evidence streams, SCAN-B / TCGA / I-SPY2 outcomes
**Out:** `artifacts/v2/conformal_model.pkl`
**Gate:** empirical coverage within 2% of nominal
**Runtime:** ~30 min

Replace Q5's `0.60/0.25/0.15`. Feature vector per (patient, drug): ODE-predicted effect, Q2
sensitivity projection, GCTX reversal percentile, network-evidence score, predicted synergy with
standard-of-care.

```python
from mapie.regression import MapieRegressor
mapie = MapieRegressor(estimator=base, method="plus", cv=10).fit(X_cal, y_cal)
y_pred, y_pis = mapie.predict(X_test, alpha=0.10)
coverage = ((y_test >= y_pis[:, 0, 0]) & (y_test <= y_pis[:, 1, 0])).mean()
gate("NB13", "conformal_coverage_90", abs(coverage - 0.90), 0.02, direction="lte")
```

**Nest v1 as a special case.** Set the Bayesian prior on the weights *at* Q5's current values.
Then the posterior tells you directly whether the data moves them, which is a clean and honest
comparison rather than an assertion that the old weights were wrong.

**If SCAN-B access hasn't arrived:** run the hierarchical Bayesian fallback on TCGA survival +
the existing GSE pCR cohorts. Same interface, wider intervals, and you swap in SCAN-B when it
lands.

---

## 8. NB14 — the end-to-end demo

**In:** everything
**Out:** `reports/v2/single_patient_walkthrough.html`
**Gate:** `safety.assert_safe()` passes on every generated string
**Runtime:** ~5 min per patient

This is the notebook you show people. One patient, start to finish:

1. Load raw three-view profile
2. Harmonise → deconvolve → intrinsic expression
3. Encode → latent posterior **with uncertainty ellipse plotted**
4. Pathway + TF activity, methylation-reliability flags shown
5. CARNIVAL network rendered
6. ODE simulation for top candidates — **trajectory plots, not scores**
7. Synergy matrix with the predicted resistance path annotated
8. Conformal prediction set
9. Every generated string passed through `pipeline_core.safety.assert_safe`

Then run the same patient through **v1** and show both side by side. That comparison is your
results section and your demo.

**Extend the safety gate now.** The ODE introduces new failure modes — a simulated trajectory
must never be presented as an expected clinical course. Add to `BANNED_PHRASES`:
`will respond`, `expected response duration`, `predicted survival`, `weeks of response`,
`time to progression`. Test that `assert_safe` raises on each.

---

## 9. Promotion path: notebook → app

Only after a phase's gates pass.

| Notebook | Promotes to | Replaces |
|---|---|---|
| NB01 | `pipeline_core_v2/harmonise.py` | new |
| NB02 | `jobs/build_deconvolution_artifact.py` | new (host-only, like existing GCTX jobs) |
| NB04–05 | `pipeline_core_v2/latent.py` | `cluster_model.py` |
| NB06 | `pipeline_core_v2/functional.py` | `signatures.py`, `residual_signatures.py` |
| NB07 | `jobs/build_carnival_networks.py` | new |
| NB09–11 | `pipeline_core_v2/ode.py` | `gctx_retrieval.py` as primary ranker |
| NB12 | `pipeline_core_v2/transfer.py` | new |
| NB13 | `pipeline_core_v2/fusion.py` | Q5 weights |

**Promotion rules:**

- Lift the *compute* cell only. Loading and plotting stay in the notebook.
- Every promoted function gets a test in `application/packages/pipeline_core/tests/` mirroring
  the existing 14-file suite.
- **Extend `_timed_audit` in `analysis_service.py` to the new stages.** The 8-stage audit trail
  is one of the best things about the current app; v2 stages must appear in it or the technical
  view goes stale.
- Wire the `pipeline_core` test suite into CI. Currently `.github/workflows/` runs only the root
  `pytest -q` smoke test — neither the `pipeline_core` suite nor the web tests run on PRs. Fix
  this before Phase 2 lands, not after.
- `LIMITATIONS.md` is updated **in the same PR** as each stage. The document's own contract — "if
  the UI contradicts this document, that is a bug" — makes a lagging update a shipped bug.

---

## 10. Schedule and failure branches

| Phase | Notebooks | Weeks | Blocking gate |
|---|---|---|---|
| 0 | NB00 | 0.5 | sources present |
| 1 | NB01–03 | 3 | PAM50 ≥0.85; purity ρ≥0.7 |
| 2 | NB04–05 | 4 | VAE beats MOFA+ |
| 3 | NB06–08 | 3 | DepMap AUROC ≥0.65; **RNA↔protein ≥0.6** |
| 4 | NB09–11 | 6–8 | GDSC ρ≥0.4; **ALMANAC synergy ρ≥0.3** |
| 5 | NB12–13 | 3 | coverage ±2% |
| Demo | NB14 | 1 | safety passes |

**Failure branches, decided in advance so you don't rationalise later:**

- **NB01 fails** → escalate through the harmonisation ladder (rank → z-score → ComBat). If all
  three fail, drop TCGA and run METABRIC-only. Phases 2–5 still work; you lose outcome labels and
  fall back to the Bayesian fusion in NB13.
- **NB04 fails** → MOFA+ fallback, pre-declared. Costs you nothing but the nonlinearity.
- **NB08 fails** → Phase 4 does not proceed as specified. Narrow the node set, or switch to
  phospho-based personalisation, or stop at Phase 3+5.
- **NB11 fails** → ODE doesn't earn its complexity. Write up the negative result. Phases 1–3 and 5
  are still a complete pipeline that is strictly better than v1.

Phases 1–3 and 5 are independently valuable and don't depend on the ODE working. Sequence the
writeup so that a Phase 4 negative result still leaves you with a paper.

---

## 11. First week

1. Create the directory layout (§0.3) and `_gate.py` (§0.4).
2. **Submit the SCAN-B access request.** Longest lead time in the project.
3. Install both environments; verify `diffrax`, `decoupler`, and `CARNIVAL` import cleanly.
4. Write NB00, download METABRIC + TCGA + OmniPath, populate the manifest.
5. Write NB01 and run the PAM50 gate.

If NB01 passes in week one, the rest of Phase 1 is mechanical and you'll know within three weeks
whether the deconvolution fix meaningfully changes the v1 ranking — which is the first real
result on the board.
