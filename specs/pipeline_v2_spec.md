# Pipeline v2 specification
## Multi-omic latent state → causal network → mechanistic drug-response simulation

**Repo:** `Lifework-Health/person_med_a2`
**Status:** design proposal, not yet implemented
**Supersedes:** the Q1 (MOFA/NBS) → Q4 (GCTX retrieval) → Q2 (viability) → Q5 (heuristic prioritisation) chain

---

## 0. Purpose and scope

### 0.1 Goal statement

Given one patient's **RNA-seq, copy-number (CNA), and DNA methylation** profile, produce a
clinician-facing overview that states:

1. Where this patient sits in a continuous multi-omic state space, **with calibrated uncertainty**.
2. Which signalling nodes are inferred to be causally active, and why.
3. Which interventions the model predicts will move that state, **at achievable doses, over time**.
4. Which combinations are predicted synergistic, **including pairs never assayed together**.
5. Where resistance is predicted to emerge, and what second agent addresses it.
6. An explicit, machine-checked statement of what the system does *not* know.

### 0.2 Non-goals

This is a research prototype. It is not clinical decision support, and nothing in this spec
changes that. The existing safety architecture — `pipeline_core/safety.py`, the abstention
logic, and `LIMITATIONS.md`'s "if the UI contradicts this document, that is a bug" contract —
is **retained in full** and extended, not replaced.

### 0.3 Design principle

> Every number the clinician sees must be traceable to either (a) a fitted model with a
> held-out validation score, or (b) a declared prior. No number may be the output of a
> hand-chosen weight that was never fitted to anything.

The current pipeline violates this in exactly one place, and that place is Q5. See §1.5.

---

## 1. What v1 does, and its five failure modes

### 1.1 The current chain, precisely

| Stage | Script | What it does |
|---|---|---|
| Q1 | `scripts/q1/mofa.py` | MOFA on RNA + CNA + methylation → 5 hard clusters |
| Q1 | `scripts/q1/nbs.py` | Network-based stratification (parallel, unused downstream) |
| Q4 | `scripts/q4/run_mofa_cluster_q4.py` | Per-cluster signature → LINCS L1000 GCTX reversal → ranked drugs |
| Q2 | `scripts/q2_run_pipeline_v2.py` | Elastic-net cell-viability models fit on cell lines, projected onto patient expression |
| Q5 | `scripts/Q5.R` (4,426 lines) | Weighted sum of Q2 + Q4 + NCI-ALMANAC combination evidence |
| App | `application/` | FastAPI + Next.js surface over the committed outputs |

At inference the app cannot use CNA or methylation, so `pipeline_core/cluster_model.py` trains
an **RNA-only elastic-net surrogate** to guess the MOFA cluster back from expression alone
(macro-F1 ≈ 0.76 by 5-fold CV).

### 1.2 Failure mode 1 — discretisation destroys the signal

MOFA yields a continuous latent manifold. v1 collapses it to 5 labels, then estimates
signatures by regressing gene expression on cluster dummies plus PAM50.

Two problems compound:

- **Collinearity.** PAM50 subtype and MOFA cluster membership are substantially correlated in
  breast cancer — both are driven largely by the same proliferation/hormone-receptor axes. In a
  design matrix containing both, the "cluster effect" is only whatever variance PAM50 failed to
  absorb. That is not a stable estimand: re-run MOFA with a different seed or a different number
  of factors and the coefficients move.
- **Information loss.** A patient at the boundary between cluster 2 and cluster 3 is assigned to
  one of them, and every downstream computation treats them as a prototypical member. The
  *distance* to the centroid — arguably the most clinically informative quantity — is discarded.

### 1.3 Failure mode 2 — the surrogate classifier is self-inflicted

The classifier exists only because the inference path was built RNA-only. Its consequences ripple:
three configuration thresholds (`MIN_GENE_COVERAGE=0.6`, `LOW_CONFIDENCE_THRESHOLD=0.40`,
`ABSTENTION_THRESHOLD=0.25` in `pipeline_core/config.py`) exist purely to paper over the fact
that a softmax over a lossy classifier is not a real posterior. `LIMITATIONS.md` §4 states the
problem honestly but cannot solve it: *"a 'high confidence' prediction is still a proxy, not a
re-derivation of the ground-truth multi-omics cluster."*

If patients have all three modalities — which is the stated premise — this entire subsystem is
unnecessary. See §4.

### 1.4 Failure mode 3 — bulk confounding is unhandled and undeclared

METABRIC expression is bulk tissue: typically 30–60% stroma, immune infiltrate, and normal
epithelium by transcript mass. Q2's viability models are fit on **pure cell lines**. Projecting
a cell-line-derived coefficient vector onto bulk tumour expression therefore measures a mixture
of tumour-intrinsic signal and microenvironment composition.

This is a **systematic bias, not noise** — it correlates with subtype (immune-hot TNBC vs.
stroma-rich lobular), so it will bias the drug ranking in a subtype-dependent direction. It is
not mentioned anywhere in `LIMITATIONS.md`, which makes it the most serious undeclared issue in
the current system.

### 1.5 Failure mode 4 — Q5 is a ranking convention, not a model

From `scripts/Q5.R` lines 59–66:

```r
  # Transparent heuristic weights. These are not fitted on patients.
  single_weight_patient_sensitivity = 0.60,
  single_weight_q2_reliability      = 0.25,
  single_weight_q4_support          = 0.15,

  combination_weight_components = 0.55,
  combination_weight_almanac    = 0.35,
  combination_weight_q4         = 0.10,
```

The comment is admirably honest. But it means the final patient-facing ranking is a declaration,
not an inference. It has no likelihood, no uncertainty, and cannot be falsified — if the ranking
is wrong, there is no parameter to update. The remaining ~4,300 lines of `Q5.R` are plumbing:
NSC→drug-name mapping, ALMANAC table import, and a cell-line alignment gate. Valuable
engineering, but it produces no new inference.

### 1.6 Failure mode 5 — connectivity reversal has no pharmacology, and no target state

Two distinct problems:

**No dose, no time.** A GCTX reversal percentile asks: does compound *X*'s transcriptional
signature, measured in MCF7 at one concentration and one timepoint, anti-correlate with the
patient's signature? A compound that reverses beautifully at 10 µM in a dish but cannot exceed
0.5 µM in human plasma is indistinguishable from one that is achievable. The pipeline has no
representation in which that distinction can even be stated.

**No target state.** `LIMITATIONS.md` §9 says it plainly: reversing a cluster signature moves
*away from that cluster*, not *toward health*. Because the reference is one-vs-rest among
METABRIC tumours, the optimisation has no fixed point that corresponds to a desirable state.

**No unassayed combinations.** ALMANAC contributes only pairs somebody physically ran. The
combinatorial space is untouched.

---

## 2. Target architecture

```
   RNA-seq        CNA         Methylation
      │            │              │
      ▼            ▼              ▼
  ┌───────────────────────────────────┐
  │ S0  Harmonisation + QC            │
  │ S1  Deconvolution → intrinsic     │
  └───────────────────────────────────┘
                  │
                  ▼
  ┌───────────────────────────────────┐
  │ S2  Product-of-experts VAE        │  ← replaces MOFA + surrogate classifier
  │     joint posterior q(z | views)  │
  └───────────────────────────────────┘
                  │
                  ▼
  ┌───────────────────────────────────┐
  │ S3  Functional / causal layer     │  ← replaces OLS gene signatures
  │     PROGENy → CollecTRI → CARNIVAL│
  └───────────────────────────────────┘
                  │
                  ▼
  ┌───────────────────────────────────┐
  │ S4  Personalised logic-ODE        │  ← replaces GCTX reversal ranking
  │     dose, time, feedback, synergy │
  └───────────────────────────────────┘
                  │
                  ▼
  ┌───────────────────────────────────┐
  │ S5  Domain adaptation (PRECISE)   │
  │ S6  Conformal calibration         │  ← replaces Q5 heuristic weights
  │ S7  Clinician surface             │
  └───────────────────────────────────┘
```

Uncertainty propagates end-to-end: posterior width from S2 → sampled initial conditions in S4 →
prediction-set width in S6.

---

## 3. S0/S1 — Harmonisation and deconvolution

### 3.1 The METABRIC ↔ TCGA normalisation problem

This is the first hard problem, because v2 requires both cohorts (METABRIC for continuity with
existing outputs; TCGA-BRCA for outcomes, purity, and true RNA-seq).

**Why naive merging fails.** METABRIC is Illumina HT-12 microarray: intensity-based,
log-normal-ish, compressed dynamic range, saturating at high expression, with a floor at
background hybridisation. TCGA-BRCA is Illumina RNA-seq: count-based, negative-binomial,
effectively unbounded above, with true zeros. Quantile-normalising one to the other creates
artefacts precisely at the extremes — which is exactly where signature genes live.

**Recommended approach, in order of preference:**

1. **Rank-based within-cohort transformation.** Convert each sample to within-sample gene ranks,
   then to a normal score (inverse-normal transform). This discards absolute magnitude — which
   is not comparable across platforms anyway — and retains within-patient relative ordering,
   which is what every downstream footprint method actually consumes. PROGENy, VIPER/aREA, and
   `decoupleR` are all rank-based or rank-robust, so nothing is lost. This is the default.

2. **Cohort-specific z-scoring against a cohort-matched reference.** Compute z-scores against the
   *same platform's* distribution, never a pooled one. Sample-level z is then comparable
   across platforms in the way a percentile is comparable, without pretending the raw scales match.

3. **`ComBat` / `removeBatchEffect` with cohort as batch and biological covariates protected.**
   Only if 1 and 2 prove insufficient, and only with subtype + purity + stage explicitly
   protected in the model matrix. Batch correction across platforms with confounded biology is a
   known way to erase real signal; treat this as a last resort and always report the
   pre/post-correction subtype separation.

**What NOT to do:** do not train the VAE on pooled raw values. Train per-view encoders on
rank-normalised input with a cohort indicator available to an adversarial/conditional head, so
platform is modelled rather than assumed away.

**Validation gate:** after harmonisation, a PAM50 classifier trained on METABRIC must achieve
≥0.85 concordance with the published TCGA PAM50 calls. If it does not, the harmonisation is
broken and no downstream result is interpretable.

### 3.2 What deconvolution is, and why it matters here

**The problem.** A bulk RNA-seq measurement of a tumour biopsy is a weighted average of the
transcriptomes of every cell in that biopsy — malignant epithelium, fibroblasts, T cells,
macrophages, endothelium, normal epithelium. You observe the mixture; you want the components.

**Deconvolution** is the inverse problem: given the bulk profile and a reference describing what
each cell type's transcriptome looks like, estimate (a) the **proportions** of each cell type and
ideally (b) the **cell-type-specific expression profile** within this particular sample.

#### CIBERSORTx

<cite index="53-1">CIBERSORTx is a machine learning method that infers cell-type-specific gene expression profiles without physical cell isolation, and by minimizing platform-specific variation it also allows single-cell RNA-sequencing data to be used for large-scale tissue dissection.</cite> It works by support-vector regression against a *signature matrix* (a genes × cell-types reference), with an added "imputation" step that recovers per-sample, per-cell-type expression. Its predecessor CIBERSORT's LM22 immune signature matrix is the most widely used reference in the field. Practical constraint: the full pipeline runs on a central Stanford server, which matters for a local-first architecture.

#### BayesPrism

<cite index="55-1">BayesPrism ("Bayesian cell proportion reconstruction inferred using statistical marginalization") is a Bayesian method that predicts cellular composition and gene expression in individual cell types from bulk RNA-seq, using patient-derived scRNA-seq as prior information.</cite> Rather than regression, it places a prior over cell-type-specific expression drawn from a single-cell reference and jointly infers proportions and per-sample expression by marginalising over the latent assignment of reads to cell types. Two consequences matter for us: it returns **posterior distributions** rather than point estimates (so uncertainty propagates into S2), and it runs locally as an R package rather than requiring a server.

**Which to use.** There is a breast-cancer-specific benchmark. <cite index="60-1">Tran et al. simulated thousands of bulk mixtures from breast tumour scRNA-seq to compare nine deconvolution methods, and found that BayesPrism and DWLS have the lowest combined numbers of false positives and false negatives, with the best performance on granular immune lineages.</cite> The same study raises a caution directly relevant to us: <cite index="42-1">most methods tend to mis-predict normal epithelial cells as cancer epithelial cells as tumour purity increases, and the breast cancer molecular subtype influences this mis-prediction.</cite>

**Decision: BayesPrism primary, DWLS as a concordance check.** Reference: the Wu et al. breast
cancer single-cell atlas.

### 3.3 The normal-breast reference

Add **GTEx breast** and **TCGA-BRCA adjacent normals** as a reference distribution. This converts
the optimisation target from "away from cluster *k*" to "toward the normal-breast manifold,"
which is a fixed point that actually corresponds to something desirable. This alone resolves the
first bullet of `LIMITATIONS.md` §9.

Caveat to declare: GTEx breast is predominantly adipose-rich tissue from post-mortem donors and
is not a clean epithelial reference. Use it *after* deconvolution, comparing epithelial
compartment to epithelial compartment.

### 3.4 S0/S1 outputs

| Artifact | Content |
|---|---|
| `harmonised_expression.parquet` | Rank-normalised, per-cohort, with platform tag |
| `deconvolution_posterior.parquet` | Per-sample cell-type proportions with credible intervals |
| `intrinsic_expression.parquet` | Malignant-compartment expression, per sample |
| `purity_estimates.parquet` | From CNA (ASCAT/ABSOLUTE) and from deconvolution — reported separately, concordance checked |

---

## 4. S2 — Product-of-experts variational autoencoder

### 4.1 What a VAE is

A variational autoencoder learns a probabilistic mapping between observed data **x** and a
low-dimensional latent **z**. Two networks are trained jointly:

- an **encoder** (inference network) `q_φ(z | x)`, which outputs the parameters of a distribution
  over **z** — for a Gaussian, a mean vector μ and a variance vector σ².
- a **decoder** (generative network) `p_θ(x | z)`, which reconstructs the data from **z**.

Training maximises the evidence lower bound (ELBO): reconstruction quality minus a KL divergence
that pulls `q_φ(z|x)` toward a prior `p(z)`, usually a standard normal. The key property for our
purposes: the encoder returns a **distribution**, not a point. Its width is a first-class,
learned statement of how much the data constrains the latent state.

### 4.2 What "product of experts" adds

With multiple modalities you need `q(z | x_RNA, x_CNA, x_METH)`. The naive approach requires a
separate encoder for every subset of available views — 2³−1 = 7 encoders for three modalities,
exponential in general.

The product-of-experts (PoE) construction solves this. <cite index="65-1">Wu and Goodman introduced the multimodal VAE (MVAE), which uses a product-of-experts inference network and a sub-sampled training paradigm; notably the model shares parameters to efficiently learn under any combination of missing modalities.</cite> <cite index="64-1">Assuming conditional independence among the modalities, the correct inference network is a product-of-experts, a structure which reduces the number of inference networks to one per modality.</cite>

**The mechanism.** Each modality *m* gets its own encoder producing a Gaussian
`q_m(z|x_m) = N(μ_m, σ_m²)`. The joint posterior is the normalised product of these Gaussians
together with the prior. For Gaussians this has a closed form in precision (inverse variance):

```
T_m  = 1 / σ_m²                     (precision of expert m)
μ_joint = Σ_m (T_m · μ_m) / Σ_m T_m
σ²_joint = 1 / Σ_m T_m
```

Read what this does:

- **Each expert votes with weight equal to its confidence.** A modality that is uninformative
  about a given latent dimension has low precision there and barely moves the mean.
- **Missing a modality means dropping a term from the sum.** No retraining, no imputation, no
  separate model. The patient with RNA only lands in the *same* latent space as the patient with
  all three.
- **Missing views widen the posterior automatically.** Fewer precision terms in the denominator
  → larger `σ²_joint`. Uncertainty from incomplete data is now *derived*, not thresholded.

<cite index="66-1">The MVAE was a marked improvement over previous approaches, modelling the joint posterior as a product of experts over the marginal posteriors, enabling cross-modal generation at test time without requiring additional inference steps.</cite>

The sub-sampled training paradigm matters: fully-observed training examples are treated as both
fully and partially observed within each gradient update, so the unimodal encoders learn to be
individually competent rather than only useful in combination.

### 4.3 Configuration for this project

| Component | Choice |
|---|---|
| Views | RNA (intrinsic compartment), CNA (segment-level log-ratio), methylation (promoter/enhancer β collapsed to region level) |
| Encoders | 2-layer MLP per view, view-specific input dimension, shared latent dim `d = 32` |
| Decoders | Gaussian for RNA rank-normal, Gaussian for CNA, Beta for methylation β-values |
| Prior | `N(0, I)` |
| Training | Sub-sampled ELBO (Wu & Goodman); each batch includes full and randomly-masked view subsets |
| Platform handling | Cohort indicator fed to a small adversarial head; gradient reversal to discourage platform-separable latents |

### 4.4 What this replaces, concretely

| v1 component | Fate |
|---|---|
| `pipeline_core/cluster_model.py` (elastic-net surrogate) | **Deleted** |
| `MIN_GENE_COVERAGE` | **Deleted** — coverage enters through per-gene encoder masking |
| `LOW_CONFIDENCE_THRESHOLD` | **Replaced** by a posterior-entropy threshold with a stated calibration target |
| `ABSTENTION_THRESHOLD` | **Replaced** by a posterior-width threshold, calibrated so abstention rate on held-out full-view data is <2% |
| 5 hard clusters | **Retained as a presentation layer only** — computed post-hoc from the latent posterior, with membership = actual posterior mass under a Gaussian-mixture fit |

Clinicians want a label. They should get one. The system just must not *compute* on it.

### 4.5 Alternative considered

MOFA+ (Argelaguet et al.) natively handles missing views and is the incumbent's natural upgrade.
It is a reasonable fallback and is more interpretable (linear loadings). It is rejected as
primary because the linearity that makes it interpretable also limits its ability to represent
the nonlinear coupling between methylation state and expression that S3 depends on. **If the PoE-VAE
underperforms MOFA+ on held-out reconstruction, fall back — and say so in the paper.**

---

## 5. S3 — Functional and causal layer

This replaces gene-level OLS signatures with pathway, TF, and network-level state. Four
components, each explained.

### 5.1 PROGENy — pathway activity from perturbation footprints

**The problem it solves.** The intuitive way to score a pathway is to average the expression of
its member genes. This is wrong for signalling pathways, for a reason the PROGENy authors state
directly: <cite index="76-1">mapping gene expression to pathway components disregards the effect of post-translational modifications, and downstream signatures represent very specific experimental conditions.</cite> MAPK activity is regulated by phosphorylation cascades — the *transcript* levels of MAPK pathway members tell you almost nothing about whether the pathway is *on*.

**The insight.** Instead of looking at the pathway's members, look at its **footprint** — the
genes whose expression *changes downstream* when the pathway is perturbed. <cite index="76-1">PROGENy overcomes both limitations by leveraging a large compendium of publicly available perturbation experiments to yield a common core of Pathway RespOnsive GENes.</cite>

**What it delivers.** ~14 signalling pathways (EGFR, MAPK, PI3K, p53, TNFα, NFκB, Hypoxia,
Trail, VEGF, JAK-STAT, Estrogen, Androgen, WNT, TGFβ), each scored per sample by a weighted sum
over its footprint genes. <cite index="76-1">PROGENy can recover the effect of known driver mutations, provide or improve strong markers for drug indications, and distinguish between oncogenic and tumor suppressor pathways for patient survival.</cite>

Critically for bulk data: footprint methods are far more robust to the noise and compression that
plague bulk microarray than gene-level statistics are.

### 5.2 DoRothEA and CollecTRI — transcription factor activity

**The same footprint logic, one level down.** A transcription factor's activity is not its own
mRNA level; it is visible in the coordinated behaviour of the genes it regulates. The set of
genes a TF regulates is its **regulon**.

**DoRothEA** is the regulon resource. It is <cite index="83-1">a gene set resource containing signed transcription factor–target interactions, curated and collected from different types of evidence such as literature-curated resources, ChIP-seq peaks, TF binding site motifs, and interactions inferred directly from gene expression. Each interaction is assigned a confidence level from A (highest) to E (lowest).</cite> Standard practice is to use confidence levels A and B only. It is typically paired with VIPER/aREA, which computes a normalised enrichment score for each regulon and — importantly — <cite index="100-1">takes into account the effect (activation or repression) of the TF on each target.</cite>

**CollecTRI** is its successor and should be the default. <cite index="89-1">The CollecTRI-derived regulons represent 45,856 signed TF–gene interactions for 1,183 TFs. Benchmarked against DoRothEA, ChEA3, RegNetwork and Pathway Commons, the CollecTRI-derived regulons outperformed the other networks in accurately inferring changes in TF activities in TF perturbation experiments collected in the KnockTF data.</cite>

**decoupleR** is the execution engine — an ensemble of activity-inference methods (aREA, ULM,
MLM, WSUM) over any regulon resource, so you can report consensus scores rather than betting on
one statistic.

### 5.3 OmniPath — the prior knowledge network

**What it is.** A meta-database that aggregates literature-curated signalling pathway resources
into a single queryable network of **signed and directed** protein–protein interactions
("A activates B", "C inhibits D"), plus TF–target relations, enzyme–substrate relations, and
protein complex annotations.

**Why it matters here.** It is the structural prior for both S3 and S4. Without it, network
inference is unconstrained and the ODE in S4 has no topology. With it, both are constrained to
edges someone has actually observed. This is what makes the ODE identifiable (§6.6).

Canonical reference: Türei, Korcsmáros & Saez-Rodriguez, *Nature Methods* 13:966–967 (2016).

### 5.4 CARNIVAL — from footprints to causal networks

**The gap it fills.** PROGENy gives pathway activities. CollecTRI gives TF activities. Neither
tells you *what upstream event caused them*. <cite index="34-1">Changes in gene expression are generally indirect consequences of upstream dysregulation, and it is often important to understand what caused it.</cite>

**What CARNIVAL does.** <cite index="34-1">CARNIVAL (CAusal Reasoning pipeline for Network identification using Integer VALue programming) is a causal network contextualization tool which derives network architectures from gene expression footprints, integrating signed and directed protein–protein interactions, transcription factor targets, and pathway signatures.</cite> <cite index="24-1">The aim is to identify a subset of interactions from a prior knowledge network that represent potential regulated pathways linking known or potential targets of perturbation towards active transcription factors derived from expression data.</cite>

**The mechanism.** It is an integer linear program. <cite index="36-1">CARNIVAL casts flow derivation as an integer linear programming optimization problem, formulated to find a flow in a parsimonious manner, with binary indicators representing activation and inhibition of each node and a regularization term that penalizes the use of additional nodes or edges.</cite> In words: find the smallest sign-consistent subnetwork of OmniPath that explains the observed TF activities.

**Two modes matter to us.** <cite index="36-1">CARNIVAL is available in two modes: standard (StdCARNIVAL), which uses prior knowledge of perturbed regulators as input, and inverse (InvCARNIVAL), which jointly infers both the upstream regulators and the signaling pathways leading to the observed downstream alterations.</cite> Use **StdCARNIVAL** when a driver mutation is known (constrain that node's sign from the CNA/mutation data); **InvCARNIVAL** otherwise.

<cite index="34-1">The use of prior knowledge in CARNIVAL enables capturing a broad set of upstream cellular processes and regulators, leading to a higher accuracy when benchmarked against related tools.</cite>

**Solver note:** CPLEX (free via IBM Academic Initiative) or open-source CBC. lpSolve will not
scale to genome-wide PKNs.

### 5.5 Where CNA and methylation earn their place

This is the answer to "why bother with three modalities at all," and it is not "more features."

| Modality | Role in S3 |
|---|---|
| **CNA** | Node **dosage priors** for CARNIVAL — an amplified gene gets a prior toward higher basal node activity, a deleted one toward lower. Also supplies tumour purity and genome-instability/HRD scores, the latter feeding PARP-inhibitor reasoning directly. |
| **Methylation** | **Regulatory gating.** Promoter hypermethylation at a TF's binding sites means that TF's regulon is unavailable regardless of TF protein abundance. This modulates the *reliability* of a CollecTRI activity estimate — a high inferred activity for a TF whose targets are methylation-silenced is a red flag, not a finding. |
| **RNA** | The observation layer everything else is inferred from. |

Note the asymmetry: CNA and methylation are not scored and averaged with RNA. They **constrain
the inference** that RNA drives. That is a different and much more defensible use.

### 5.6 S3 outputs

`pathway_activity.parquet`, `tf_activity.parquet`, `causal_network.json` (per patient),
`network_confidence.parquet` (methylation-gated reliability per TF).

---

## 6. S4 — Personalised logic-ODE drug response model

This is the novel component. It is also the risky one; §6.6 is not optional reading.

### 6.1 The idea

Build a **small mechanistic dynamical model** of the signalling network, personalise it with the
patient's omics, and *simulate* what happens when you inhibit one or two nodes at clinically
achievable concentrations.

Not a whole-cell model. Not a genome-scale model. A 40–60 node ODE over the signalling axes that
matter in breast cancer.

### 6.2 Why logic-ODE specifically

Two extremes exist. Boolean networks are qualitative — a node is on or off, and you get no dose
or time. Full mass-action ODEs need kinetic rate constants nobody has measured for most of the
network.

**Logic-ODEs** sit between. You start from a Boolean logic network (which OmniPath gives you) and
convert each logic gate into a continuous ODE using normalised Hill functions, so the system
inherits the Boolean topology's interpretability while gaining continuous state, time evolution,
and dose response. Each node *i* follows:

```
dx_i/dt = τ_i · ( B_i(x) − x_i )
```

where `B_i(x)` is the continuous ("HillCube") interpolation of the Boolean update rule over
node *i*'s regulators, and `τ_i` sets its response timescale. Each edge contributes a normalised
Hill term with parameters *k* (sensitivity) and *n* (cooperativity).

The foundational transformation is Wittmann et al., *BMC Systems Biology* 3:98 (2009),
"Transforming Boolean models to continuous models: interpolation and the HillCube"; the
implementation lineage runs through Odefy (Krumsiek et al., *BMC Bioinformatics* 11:233, 2010)
into `CellNOptR`/`CNORode` (Terfve et al., *BMC Systems Biology* 6:133, 2012).

### 6.3 The precedent — this has been done, and it worked

The design here is a direct adaptation of the Saez-Rodriguez group's logic-ODE work.

**Eduati et al. 2017** is the anchor paper. <cite index="4-1">Eduati F, Doldàn-Martelli V, Klinger B, Cokelaer T, Sieber A, Kogera F, Dorel M, Garnett MJ, Blüthgen N, Saez-Rodriguez J. "Drug Resistance Mechanisms in Colorectal Cancer Dissected with Cell Type–Specific Dynamic Logic Models." Cancer Res. 2017;77(12):3364–3375. doi:10.1158/0008-5472.CAN-17-0078</cite>

The design: <cite index="4-1">they measured 14 phosphoproteins under 43 different perturbed conditions (combinations of 5 stimuli and 7 inhibitors) in 14 colorectal cancer cell lines, building cell-line-specific dynamic logic models.</cite> The result that matters most for us: <cite index="9-1">model parameters, representing pathway dynamics, were used as features to predict sensitivity to a panel of 27 drugs. This analysis revealed associations between cell-specific signaling pathways and drug sensitivity for 14 of the drugs, 9 of which have no genomic biomarker.</cite>

Read that last clause carefully: **nine drugs whose sensitivity was predictable from signalling
dynamics but not from any genomic biomarker.** That is precisely the gap a mutation- or
expression-signature-based pipeline cannot close, and it is the strongest single argument for
adding S4.

And it produced a validated combination: <cite index="9-1">following one of these associations, they validated a drug combination predicted to overcome resistance to MEK inhibitors by co-blockade of the relevant node.</cite>

**Eduati et al. 2020** extends the method from cell lines to actual patient material. <cite index="20-1">Eduati F, Jaaks P, Wappler J, Cramer T, Merten CA, Garnett MJ, Saez-Rodriguez J. "Patient-specific logic models of signaling pathways from screenings on cancer biopsies to prioritize personalized combination therapies." Mol Syst Biol. 2020;16(2):e8664. doi:10.15252/msb.20188664</cite> — <cite index="20-1">an approach that couples ex vivo high-throughput screenings of cancer biopsies using microfluidics with logic-based modeling to generate patient-specific dynamic models of extrinsic and intrinsic apoptosis signaling pathways, used to investigate heterogeneity in pancreatic cancer patients.</cite>

**The honest caveat, stated up front:** both papers calibrate on *perturbation* data — phosphoproteomic
readouts under systematic stimulus/inhibitor combinations. We do not have that for METABRIC
patients and cannot generate it. Our substitute is baseline-omics calibration, which is a weaker
constraint. This is a known and studied compromise: <cite index="11-1">comprehensive perturbation data covering a wide range of drug combinations is often not conveniently available for model calibration, even for pre-clinical systems, due to the cost of experiments; strategies to calibrate cell-specific models with baseline molecular data is a field which has up to now only been modestly studied.</cite> That paper (Niederdorfer et al., *Front Physiol* 2020) is the methodological reference for doing it anyway, and its finding — that baseline activity profiles combining large-scale omics with high-quality small-scale data give the best true/false positive ratio — is the recipe we follow.

**Scale alternative.** If the 40–60 node scope proves too narrow, the large-scale route is
Fröhlich et al., *Cell Systems* 7(6):567–579 (2018), which <cite index="19-1">developed a large-scale mechanistic model of cancer signaling that can be individualized using sequencing data, parameterized from thousands of drug assays from over 100 human cancer cell lines.</cite> Its framework <cite index="7-1">reduces computation time by multiple orders of magnitude compared to state-of-the-art methods</cite> — necessary, because naive parameterisation of a model that size is computationally infeasible.

### 6.4 Personalisation and drug action

**Personalisation.** Node total abundance is scaled by the patient's intrinsic-compartment RNA
(S1), dosage-adjusted by CNA, and initial activity states are set from the CARNIVAL solution
(S3). Edge parameters (*k*, *n*, *τ*) are **shared across all patients** — fitted once, globally.
This is the central identifiability decision; see §6.6.

**Drug action.** A drug inhibits its target node via a Hill function of free concentration:

```
k_target(C) = k_target · 1 / (1 + (C / IC50)^h)
```

with `IC50` from ChEMBL/GDSC and `C` bounded by published plasma **Cmax** so that only clinically
achievable exposure is simulated. A compound that only works above achievable `C` is
automatically deprioritised — the thing v1 structurally cannot express.

**Readout.** Not a rank. A trajectory: proliferation index (E2F target module activity) and
apoptosis index (BAX/BCL2 balance) over simulated time.

### 6.5 The three capabilities v1 cannot have

**Dose and time.** Stated above. This is the baseline gain.

**Synergy for pairs nobody assayed.** ALMANAC only contains physically-run combinations. In the
ODE you simulate inhibiting two nodes simultaneously and the *topology generates the
interaction*: PI3K inhibition relieves RTK negative feedback → MAPK rebounds → the model predicts
MEK co-inhibition rescues. Compute in-silico Bliss or Loewe excess for any pair in the network.
The combinatorial pressure is real — <cite index="11-1">among 128 oncology compounds in the Broad Drug Repurposing Hub, testing all pairs would require 8,128 combinations</cite>, which is why in-silico prioritisation exists at all.

This inverts Q5's ALMANAC term: `0.35 × ComboScore` stops being an *input weight* and becomes a
**held-out validation target**.

**Resistance, prospectively.** Integrate forward with feedback enabled and observe which node
rebounds. That node names the second drug. The output sentence is:

> "Predicted response for ~8 weeks, then IGF1R compensation; consider adding an IGF1R inhibitor."

No component of v1 can produce a statement of that form. It is also the sentence an oncologist
most wants.

### 6.6 Identifiability — the thing that will kill this if unmanaged

Sixty nodes with per-edge (*k*, *n*) plus per-node τ is several hundred parameters. Fit against
sparse data and you will get excellent training fit and meaningless parameters.

**Mitigations, all mandatory:**

1. **Hard topology prior.** Edges come from OmniPath only. No edge learning.
2. **Global parameter sharing.** Edge parameters fitted once across the entire cell-line panel;
   only node abundances and initial conditions vary per patient. This turns hundreds of
   per-patient parameters into hundreds of parameters shared across ~1,000 cell lines.
3. **Fix cooperativity.** Set `n = 2` for all Hill terms unless a specific edge has measured
   cooperativity. Fit only *k* and τ.
4. **Structural identifiability analysis before fitting.** Run `StructuralIdentifiability.jl` on
   the reduced model. Any parameter that is structurally non-identifiable gets fixed to a
   literature prior, not fitted.
5. **Profile likelihood on the fitted parameters.** Report confidence intervals. Any parameter
   with an unbounded profile is flagged in the output and its downstream predictions are
   suppressed.

**The other core assumption to test.** Node abundance is inferred from mRNA, but mRNA ≠ protein ≠
activity. Validate against **CPTAC-BRCA** proteomics: if RNA-inferred node abundance does not
correlate with measured protein for the nodes in scope, you must know that *before* building on
it. Report the correlation per node; nodes below a threshold get wider priors.

### 6.7 Implementation

`diffrax` (JAX) so the whole system is differentiable and parameters can be fitted by
backpropagating through the solver. `CNORode` is the R alternative with the advantage of matching
the reference papers exactly, at the cost of a harder fitting loop.

**Scope discipline: start with 20 nodes and one axis.** CDK4/6–RB–E2F is the right first target —
well characterised, clinically central in breast cancer, clean E2F readout, and a real approved
drug class (palbociclib/ribociclib/abemaciclib) with abundant GDSC dose-response for validation.
Expand only after that validates.

---

## 7. S5 — Domain adaptation

**The problem.** Q2 models are fit on cell lines and applied to tumours. Cell lines lack stroma,
immune context, and 3D architecture; their expression distributions differ systematically from
tumours. This is a covariate shift that v1 does not address at all.

**PRECISE** is the recommended fix (Mourragui et al., *Bioinformatics* 35(14):i510–i519, 2019,
"PRECISE: a domain adaptation approach to transfer predictors of drug response from pre-clinical
models to tumors"). Mechanism: compute principal components independently in the cell-line and
tumour expression spaces, find the **principal vectors** — pairs of directions that are
maximally aligned between the two — and project both datasets onto the aligned subspace. Fit the
response model there. Directions that exist only in cell lines (culture artefacts) or only in
tumours (microenvironment) are dropped rather than transferred.

It is interpretable, roughly 200 lines, and requires no adversarial training. **CODE-AE** (He
et al., *Nature Machine Intelligence*, 2022) is the heavier deep alternative if PRECISE's linear
alignment proves insufficient.

Note the interaction with S1: deconvolution already removes much of the tumour-specific
microenvironment variance, so PRECISE is doing less work than it would on raw bulk. Run both;
report the gain from each separately.

---

## 8. S6 — Calibrated fusion, replacing the Q5 weights

### 8.1 With outcome labels

Available label sources, in order of value:

| Cohort | n | Label | Note |
|---|---|---|---|
| SCAN-B | ~9,000 | Treatment + outcome, RNA-seq | Badly underused; the single best validation asset available |
| TCGA-BRCA | ~1,100 | Survival, all three modalities | Also the harmonisation partner |
| I-SPY2 | ~1,000 | Neoadjuvant pCR | Arm-specific |
| GSE20194 / GSE25065 | ~500 | pCR | Already in the repo's Q5 validation |
| METABRIC | ~2,000 | Survival | Incumbent |

Fit the fusion with the evidence streams as features, then wrap in **conformal prediction**.

**Why conformal.** It is distribution-free and gives finite-sample coverage guarantees. Instead
of a point score, it emits a **prediction set**: "these 4 agents contain the best option with 90%
coverage." Set *width* is then an honest, automatic expression of uncertainty — wide for a
patient with missing views (posterior width from S2 propagates), narrow for a well-characterised
one. Clinicians read sets better than they read `0.734`.

### 8.2 Without sufficient labels

Hierarchical Bayesian fusion. Each evidence stream contributes a likelihood; the weights get
posterior distributions rather than declarations. Same interface, honest uncertainty, and the
prior can be set *at* Q5's current values — so v2 nests v1 as a special case and the comparison
is clean.

### 8.3 What is retained from v1

**Keep the streams visually separate in the UI.** The `predictor_summary.role =
"parallel_clinical_context_not_nomination"` discipline in `analysis_service.py` is a genuine
strength — it prevents correlated Q4 evidence being double-counted. v2 keeps the separation and
changes only how the combination is *estimated*.

---

## 9. S7 — Clinician surface

One page.

**Position.** Patient in continuous latent space, posterior uncertainty ellipse rendered. Cluster
label shown as a badge with true posterior mass, not softmax.

**Mechanism.** The CARNIVAL network, driver nodes highlighted, methylation-gated TFs marked as
low-reliability.

**Intervention table.** Per row: predicted trajectory sparkline, achievable-dose flag, predicted
synergy partner, evidence tier, conformal set membership, and the counterfactual —

> "Block MEK → PI3K rebounds by week 6 → consider adding alpelisib."

**Uncertainty.** Prediction set, not a score.

**Safety.** `pipeline_core/safety.py` runs unchanged over every generated string. Extend
`BANNED_PHRASES` to cover new failure modes the ODE introduces — in particular any phrasing that
presents a simulated trajectory as an observed or expected clinical course. Add regexes for
"will respond", "expected response duration", "predicted survival".

---

## 10. Validation plan

Every stage gets a falsification test. A stage that cannot fail its test does not ship.

| Stage | Test | Pass criterion |
|---|---|---|
| S0 | PAM50 concordance METABRIC↔TCGA after harmonisation | ≥0.85 |
| S1 | Deconvolution vs. pathologist purity; vs. CNA-derived purity | Spearman ≥0.7 |
| S2 | Held-out view reconstruction; latent must beat MOFA+ on the same split | Lower held-out NLL |
| S2 | Abstention calibration: abstention rate on full-view held-out data | <2% |
| S3 | CARNIVAL-inferred active nodes vs. DepMap CRISPR essentiality in matched lines | AUROC ≥0.65 |
| S3 | RNA-inferred node abundance vs. CPTAC-BRCA protein | Report per node; flag <0.3 |
| S4 | Predicted vs. observed IC50, held-out GDSC2 drugs | Spearman ≥0.4 |
| S4 | Predicted synergy vs. observed ALMANAC ComboScore, **held-out pairs** | Spearman ≥0.3 |
| S4 | Parameter profile likelihoods | All fitted parameters bounded |
| S5 | Cell-line→tumour transfer gain from PRECISE vs. no adaptation | Report delta |
| S6 | Conformal coverage on SCAN-B held-out | Empirical coverage within 2% of nominal |

The S4 synergy test is the load-bearing one. If in-silico Bliss excess does not correlate with
held-out ALMANAC ComboScore, the ODE is not earning its complexity and should be cut back to a
narrower, better-validated scope.

---

## 11. Build phases

| Phase | Weeks | Content | Risk |
|---|---|---|---|
| **1** | ~3 | S0 harmonisation + S1 deconvolution + normal reference + S5 PRECISE | Low |
| **2** | ~4 | S2 PoE-VAE; delete surrogate classifier and three thresholds | Low–medium |
| **3** | ~3 | S3 PROGENy → CollecTRI → CARNIVAL | Low |
| **4** | ~6–8 | S4 logic-ODE, 20-node CDK4/6–RB–E2F scope first | **High** |
| **5** | ~3 | S6 conformal fusion; retire Q5 weights | Medium |

Phases 1–3 are low-risk, independently useful, and independently publishable. Each improves the
existing app without requiring S4 to work. Phase 4 carries the thesis-grade novelty and the
thesis-grade risk — structure the writing so that a negative S4 result is still a paper
("mechanistic simulation does not outperform connectivity mapping for breast cancer drug
prioritisation" is a publishable finding, given a fair implementation).

**Phase 1 pays for itself immediately** — it is pure correctness, and the improvement is
measurable against the committed Q5 tables already in `outputs/`.

---

## 12. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ODE non-identifiable | High | Fatal to S4 | §6.6: fixed topology, global parameter sharing, fixed `n`, structural identifiability pre-check, profile likelihoods |
| mRNA is a poor proxy for node activity | Medium | Severe | CPTAC validation *before* building; per-node reliability weights |
| Deconvolution mis-assigns normal→cancer epithelium | Medium | Moderate | Known and quantified in Tran et al. 2023; run DWLS concordance; report purity from CNA independently |
| Cross-platform harmonisation erases real signal | Medium | Severe | Rank-based default; PAM50 concordance gate; never pooled raw values |
| PoE-VAE underperforms MOFA+ | Low–medium | Moderate | Pre-declared fallback to MOFA+; report honestly |
| Not enough outcome labels for conformal fusion | Medium | Moderate | Hierarchical Bayesian fallback with Q5 weights as prior |
| Scope creep in S4 node count | High | Moderate | Hard gate: 20 nodes validate on GDSC before any expansion |

---

## 13. References

**Multi-omic integration**
- Wu M, Goodman N. Multimodal Generative Models for Scalable Weakly-Supervised Learning. *NeurIPS 31* (2018). arXiv:1802.05335.
- Shi Y, Paige B, Torr P. Variational Mixture-of-Experts Autoencoders for Multi-Modal Deep Generative Models. *NeurIPS 32* (2019). *(MoE alternative to PoE)*
- Argelaguet R, et al. Multi-Omics Factor Analysis — a framework for unsupervised integration of multi-omics data sets. *Mol Syst Biol* (2018). *(incumbent; MOFA+ 2020 is the missing-view-capable successor)*

**Deconvolution**
- Chu T, Wang Z, Pe'er D, Danko CG. Cell type and gene expression deconvolution with BayesPrism enables Bayesian integrative analysis across bulk and single-cell RNA sequencing in oncology. *Nat Cancer* 3(4):505–517 (2022). doi:10.1038/s43018-022-00356-3
- Newman AM, et al. Determining cell type abundance and expression from bulk tissues with digital cytometry. *Nat Biotechnol* (2019). PMID: 31061481. *(CIBERSORTx)*
- Tran KA, et al. Performance of tumour microenvironment deconvolution methods in breast cancer using single-cell simulated bulk mixtures. *Nat Commun* 14:5758 (2023). doi:10.1038/s41467-023-41385-5 *(the breast-specific benchmark; method selection basis)*

**Functional and causal inference**
- Schubert M, et al. Perturbation-response genes reveal signaling footprints in cancer gene expression. *Nat Commun* 9:20 (2018). doi:10.1038/s41467-017-02391-6 *(PROGENy)*
- Garcia-Alonso L, Holland CH, Ibrahim MM, Türei D, Saez-Rodriguez J. Benchmark and integration of resources for the estimation of human transcription factor activities. *Genome Res* 29(8):1363–1375 (2019). doi:10.1101/gr.240663.118 *(DoRothEA)*
- Müller-Dott S, et al. Expanding the coverage of regulons from high-confidence prior knowledge for accurate estimation of transcription factor activities. *Nucleic Acids Res* 51(20):10934–10949 (2023). doi:10.1093/nar/gkad841 *(CollecTRI)*
- Badia-i-Mompel P, et al. decoupleR: ensemble of computational methods to infer biological activities from omics data. *Bioinformatics Advances* (2022). doi:10.1093/bioadv/vbac016
- Türei D, Korcsmáros T, Saez-Rodriguez J. OmniPath: guidelines and gateway for literature-curated signaling pathway resources. *Nat Methods* 13:966–967 (2016).
- Liu A, Trairatphisan P, Gjerga E, Didangelos A, Barratt J, Saez-Rodriguez J. From expression footprints to causal pathways: contextualizing large signaling networks with CARNIVAL. *npj Syst Biol Appl* 5:40 (2019). doi:10.1038/s41540-019-0118-z
- Alvarez MJ, et al. Functional characterization of somatic mutations in cancer using network-based inference of protein activity. *Nat Genet* 48:838–847 (2016). *(VIPER/aREA)*

**Logic-ODE modelling — the S4 basis**
- **Eduati F, Doldàn-Martelli V, Klinger B, Cokelaer T, Sieber A, Kogera F, Dorel M, Garnett MJ, Blüthgen N, Saez-Rodriguez J. Drug Resistance Mechanisms in Colorectal Cancer Dissected with Cell Type–Specific Dynamic Logic Models. *Cancer Res* 77(12):3364–3375 (2017). doi:10.1158/0008-5472.CAN-17-0078** — *primary architectural reference*
- **Eduati F, Jaaks P, Wappler J, Cramer T, Merten CA, Garnett MJ, Saez-Rodriguez J. Patient-specific logic models of signaling pathways from screenings on cancer biopsies to prioritize personalized combination therapies. *Mol Syst Biol* 16(2):e8664 (2020). doi:10.15252/msb.20188664** — *patient-level extension*
- Wittmann DM, Krumsiek J, Saez-Rodriguez J, Lauffenburger DA, Klamt S, Theis FJ. Transforming Boolean models to continuous models: interpolation and the HillCube. *BMC Syst Biol* 3:98 (2009). *(the normalised-Hill transformation)*
- Krumsiek J, Pölsterl S, Wittmann DM, Theis FJ. Odefy — from discrete to continuous models. *BMC Bioinformatics* 11:233 (2010).
- Terfve C, et al. CellNOptR: a flexible toolkit to train protein signaling networks to data using multiple logic formalisms. *BMC Syst Biol* 6:133 (2012). *(CNORode implementation)*
- Niederdorfer B, Touré V, Vazquez M, Thommesen L, Kuiper M, Lægreid A, Flobak Å. Strategies to Enhance Logic Modeling-Based Cell Line-Specific Drug Synergy Prediction. *Front Physiol* 11:862 (2020). doi:10.3389/fphys.2020.00862 *(baseline-omics calibration without perturbation data — our situation exactly)*
- Fröhlich F, et al. Efficient Parameter Estimation Enables the Prediction of Drug Response Using a Mechanistic Pan-Cancer Pathway Model. *Cell Systems* 7(6):567–579 (2018). *(large-scale alternative)*
- Béal J, Montagud A, Traynard P, Barillot E, Calzone L. Personalization of logical models with multi-omics data allows clinical stratification of patients. *Front Physiol* 9:1965 (2019).

**Domain adaptation**
- Mourragui S, Loog M, van de Wiel MA, Reinders MJT, Wessels LFA. PRECISE: a domain adaptation approach to transfer predictors of drug response from pre-clinical models to tumors. *Bioinformatics* 35(14):i510–i519 (2019).
- He D, et al. A context-aware deconfounding autoencoder for robust prediction of personalized clinical drug response from cell-line compound screening. *Nat Mach Intell* (2022). *(CODE-AE)*

---

## Appendix A — Citation confidence

Verified against primary sources during drafting: Wu & Goodman 2018; Chu et al. 2022; Newman
et al. 2019; Tran et al. 2023; Schubert et al. 2018; Garcia-Alonso et al. 2019; Müller-Dott
et al. 2023; Türei et al. 2016; Liu et al. 2019; Eduati et al. 2017; Eduati et al. 2020;
Niederdorfer et al. 2020; Fröhlich et al. 2018.

Cited from established literature but **not independently re-verified during drafting** —
confirm before submission: Wittmann et al. 2009; Krumsiek et al. 2010; Terfve et al. 2012;
Mourragui et al. 2019; He et al. 2022; Argelaguet et al. 2018; Alvarez et al. 2016;
Béal et al. 2019.
