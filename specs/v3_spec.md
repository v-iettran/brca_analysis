# v3 spec — cluster-first pipeline and interface

**Supersedes:** the S4/ODE track (cut) and B5's prediction-set framing
**Retains:** S1 deconvolution, S2 PoE-VAE, S3a PROGENy/CollecTRI, S5 PRECISE, S6 conformal survival
**Shape:** six notebooks, then an interface built on their payloads

---

## 0. Why this version

The v2 pipeline was defensible but not explainable. Every stage had a gate; no stage had a
sentence a clinician could repeat. This version keeps the validated machinery and reorganises it
around four questions that each answer in one line:

| Question | Stage | Gate |
|---|---|---|
| How many subgroups does this data support? | A1 | bootstrap stability |
| Do those subgroups differ in outcome? | A2 | log-rank at pre-registered *k* |
| What distinguishes each subgroup? | A3 | differential pathway count |
| How does each subgroup differ from normal tissue? | A4 | known-biology recovery |
| Which drugs reverse that difference, and what happened in similar cells? | A5 | known-drug positive control |

The chain is legible end to end. That is the point of the rewrite.

## 0.1 The one methodological rule

**Cluster count is chosen from structure, never from survival.**

A1 selects *k* using BIC, silhouette, and bootstrap stability — none of which touch outcome data.
That *k* is written to `data/reference/preregistered_k.json` with a timestamp. A2 then tests
survival separation *at that k only*.

The interface may let a user explore other *k*. Those views render survival curves without
*p*-values, labelled `exploratory`. This is not a UI preference; it is what keeps A2's *p* honest.

---

# Part A — the notebooks

Same conventions as `pipeline_v2_implementation.md`: header / config / load / compute / persist /
gate / figures. Files on disk between notebooks, no cross-imports. Reuse `notebooks/v2/_gate.py`.

New directory: `notebooks/v3/`. Payload target: `data/interim/v3/`.

## A1 — `NB_A1_latent_and_clusters.ipynb`

**In:** `intrinsic_expression.parquet`, `poe_vae.eqx`
**Out:** `latent_posterior_v3.parquet`, `cluster_assignments.parquet`, `model_selection.parquet`, `preregistered_k.json`
**Gate:** bootstrap ARI ≥ 0.60 at selected *k*
**Runtime:** ~20 min

Encode all TCGA samples through the committed PoE-VAE. Fit GaussianMixture for *k* ∈ [2, 8].

**Retain GMM over KMeans.** It yields posterior membership probabilities, which the cluster badge
already displays and which hard assignment would discard. Describe it in the UI as "soft k-means"
and expose `n_components`; nothing more needs explaining.

Three selection criteria, computed per *k*, **none using survival**:

```python
for k in range(2, 9):
    gmm = GaussianMixture(n_components=k, covariance_type="full",
                          n_init=10, random_state=0).fit(Z)
    bic[k] = gmm.bic(Z)
    sil[k] = silhouette_score(Z, gmm.predict(Z))
    # bootstrap stability: resample 80%, refit, compare labels on the overlap
    aris = []
    for b in range(50):
        idx = rng.choice(len(Z), int(0.8 * len(Z)), replace=False)
        lab_b = GaussianMixture(n_components=k, n_init=5,
                                random_state=b).fit_predict(Z[idx])
        aris.append(adjusted_rand_score(gmm.predict(Z[idx]), lab_b))
    stability[k] = np.mean(aris)
```

Select *k* by best stability among those within 10 BIC of the minimum. Persist with a timestamp.

```python
gate("NB_A1", "cluster_stability_ari", stability[k_star], 0.60,
     note=f"k*={k_star} bic={bic[k_star]:.0f} sil={sil[k_star]:.3f}")
```

**Also persist a 2D projection** (UMAP on latent means, fixed seed) for the scatter panel, plus
per-sample posterior width for the uncertainty ring.

**If stability fails at every k:** the latent has no discrete structure. Report the continuous
latent honestly and drop clustering from the product rather than forcing a *k*.

## A2 — `NB_A2_cluster_survival.ipynb`

**In:** cluster assignments, TCGA clinical
**Out:** `km_curves.parquet`, `survival_stats.json`
**Gate:** multivariate log-rank *p* < 0.05 at pre-registered *k*
**Runtime:** ~10 min

TCGA-BRCA supplies `OS_MONTHS` / `OS_STATUS`. Use **PFI** as the secondary endpoint — TCGA breast
OS event rates are low and follow-up is short, so PFI is often the better-powered outcome. Report
both.

```python
from lifelines.statistics import multivariate_logrank_test
res = multivariate_logrank_test(df.time, df.cluster, df.event)
gate("NB_A2", "cluster_logrank_os", res.p_value, 0.05, direction="lte",
     note=f"k={k_star} n={len(df)} events={df.event.sum()}")
```

Persist per-cluster KM step functions with confidence bands, at-risk tables, and median survival.

**The sensitivity sweep.** Compute log-rank for every *k* ∈ [2,8], apply Benjamini-Hochberg, and
persist as `survival_sensitivity.parquet` — flagged `exploratory: true`, and **never surfaced as
a significance claim in the UI**. It exists so a reviewer can see the whole surface rather than
only the pre-registered slice.

**Reality check:** this gate may fail. Molecular subtypes in breast cancer separate survival
weakly once you condition on nothing else, and n≈1,000 with ~10% events is thin. A failure here
means the clusters are molecularly real but not prognostic — which is an honest finding, and the
interface should then present clusters as descriptive rather than prognostic. Do not tune *k* to
rescue it.

## A3 — `NB_A3_cluster_characterisation.ipynb`

**In:** cluster assignments, pathway/TF activity, intrinsic expression
**Out:** `cluster_profiles.parquet`, `cluster_markers.parquet`
**Gate:** every cluster has ≥3 pathways at BH-adjusted *q* < 0.05
**Runtime:** ~15 min

For each cluster, one-vs-rest on three feature families:

| Family | Test | Output |
|---|---|---|
| PROGENy (14 pathways) | Mann-Whitney + BH | effect size, q |
| CollecTRI (top 200 TFs by variance) | Mann-Whitney + BH | effect size, q, reliability flag |
| Genes (intrinsic expression) | limma or Welch + BH | log2FC, q; keep top 50 per cluster |

Keep the methylation-reliability flag attached to every TF row — a TF that looks differential but
whose regulon is methylation-silenced is a red flag, and this is the only place that distinction
surfaces.

```python
min_sig = min(len(profiles[c].query("q < 0.05")) for c in clusters)
gate("NB_A3", "cluster_differential_pathways", min_sig, 3,
     note=f"per-cluster significant pathway counts: {counts}")
```

**Persist a comparison matrix** shaped `(clusters × features)` of signed effect sizes. That single
object drives the heatmap in B3 — build it here rather than reshaping in the frontend.

## A4 — `NB_A4_normal_reference.ipynb`

**In:** TCGA raw expression, deconvolution posterior
**Out:** `normal_reference_v3.parquet`, `cluster_vs_normal_signature.parquet`
**Gate:** signature recovers known biology (see below)
**Runtime:** ~1 h

**Extract adjacent normals.** TCGA barcodes encode sample type in positions 14–15; `11` is solid
tissue normal. Roughly 113 exist for BRCA.

```python
sample_type = barcode.str[13:15]
normals = expr[sample_type == "11"]
tumours = expr[sample_type == "01"]
```

**Deconvolve the normals too, and compare epithelium to epithelium.** Normal breast is
epithelium plus adipose; tumour is malignant plus stroma plus immune. Comparing bulk to bulk
recovers a composition difference and mislabels it a cancer signature. This is the single most
important instruction in this notebook.

**Use pairing where it exists.** Many normals are matched to a tumour from the same patient. Run
a paired test on that subset and an unpaired test on the rest; report both.

Per cluster: `signature_c = mean(intrinsic_tumour | cluster=c) − mean(intrinsic_normal)`, moderated
by limma with patient as a blocking factor on the paired subset.

**Why this matters.** v1 computed one-vs-rest among tumours, so "reversal" had no fixed point —
`LIMITATIONS.md` §9. Cluster-versus-normal has a real target state, so reversal finally means
"move toward normal breast tissue" rather than "move away from cluster *k*."

**The gate is a known-biology check.** Proliferation genes (MKI67, CCNB1, AURKA, the E2F module)
must be up in tumour-versus-normal for every cluster, and most strongly in the basal-enriched one.
If they are not, the comparison is broken.

```python
prolif_up = all(sig[PROLIF_GENES].mean() > 0 for sig in cluster_sigs.values())
gate("NB_A4", "proliferation_up_vs_normal", int(prolif_up), 1,
     note=f"per-cluster proliferation mean logFC: {means}")
```

**Caveats to carry into the UI, not bury:** adjacent normal shows field effects from neighbouring
tumour; n≈113; and the paired subset is smaller still. All three belong in the glossary entry.

## A5 — `NB_A5_drug_retrieval.ipynb`

**In:** cluster-vs-normal signatures, LINCS/GCTX, GDSC2, PRECISE projection, DepMap
**Out:** `reversal_candidates.parquet`, `nearest_cell_lines.parquet`, `dose_response_curves.parquet`
**Gates:** known-drug positive control; nearest-line subtype concordance
**Runtime:** ~2 h

### A5.1 Signature reversal

Standard connectivity scoring of `cluster_vs_normal_signature` against LINCS, restricted to breast
lines where available. Reuse the existing `gctx_retrieval` machinery — the signature changes, the
retrieval does not.

**Positive control gate.** Endocrine agents should surface for the ER-high cluster; HER2 agents for
the HER2-amplified cluster. This is weak evidence but it is checkable, and without it the panel is
unvalidated.

```python
er_hits = {"tamoxifen", "fulvestrant", "raloxifene"} & set(top50[er_cluster])
gate("NB_A5", "known_drug_positive_control", len(er_hits), 1,
     note=f"ER cluster top-50 endocrine hits: {er_hits}")
```

### A5.2 Nearest cell lines — replaces the ODE

For each patient (and each cluster centroid), find the *k*=5 most similar GDSC/DepMap lines in
**PRECISE-aligned space**. This is what PRECISE was built for; Δ+3.15 is already logged.

```python
Xs, Xt, angles = precise(cell_expr, tumour_expr, n_pc=70, n_pv=40)
sim = cosine_similarity(tumour_proj[patient], cell_proj)
nearest = np.argsort(-sim)[:5]
```

Then attach each line's **actually measured** GDSC dose-response — fitted Hill curves with the
real IC50, plus Cmax from `drug_pk.csv`.

**Why retrieval instead of simulation.** Every displayed number is a measurement. There is no
model to be wrong. It explains in one sentence: *"these five cell lines most resemble this
tumour; here is how they actually responded."* The interaction is the same slider the ODE panel
would have had, but nothing behind it is inferred.

**Gate:** nearest lines should share the patient's PAM50 subtype more often than chance.

```python
concordance = np.mean([pam50[line] == pam50[patient] for line in nearest_all])
gate("NB_A5", "nearest_line_subtype_concordance", concordance, 0.40,
     note=f"chance={baseline:.3f} n={n}")
```

Persist curves as sampled points (concentration, viability, CI) rather than fitted parameters —
the frontend should plot, not solve.

## A6 — `NB_A6_payloads.ipynb`

**In:** everything above
**Out:** `data/interim/v3/payload_{patient_id}.json`, `cohort_payload.json`
**Gate:** `safety.assert_safe` passes on every generated string
**Runtime:** ~5 min

Two payload types. **Cohort-level** (shared): projection coordinates, cluster assignments, KM
curves, model-selection curves, cluster profiles, comparison matrix. **Patient-level**: position
and posterior width, cluster membership probabilities, sample quality, prognostic interval,
reversal candidates, nearest lines with curves.

Split this way because the control board recomputes clustering across the whole cohort while the
patient panels stay fixed — the frontend should not refetch a patient when *k* changes.

**Carry the encoder identity:** `"encoder": meta["encoder"]`. If the payload came from the linear
PoE fallback rather than the committed VAE, the glossary must suppress the NLL claim. This was
open from the last review.

---

# Part B — interface

## B0. Design system

### Typography

IBM Plex Sans for UI, IBM Plex Mono for all numerals — statistics, *p*-values, concentrations,
patient IDs. Tabular figures make columns of numbers scannable and stop values jittering when they
animate.

```css
--font-sans: 'IBM Plex Sans', system-ui, sans-serif;
--font-mono: 'IBM Plex Mono', ui-monospace, monospace;
```

Scale: 12 / 13 / 14 / 16 / 20 / 28. Weights 400, 500, 600 only. Line height 1.5 body, 1.2 headings.

### Colour

```css
--bg:            #F8FAFC;   /* page */
--surface:       #FFFFFF;   /* cards */
--text-primary:  #0F172A;
--text-secondary:#475569;
--teal-primary:  #0F766E;
--teal-secondary:#14B8A6;
--molecular:     #7C3AED;   /* genomic / latent */
--progression:   #DC2626;
--response:      #16A34A;
--warning:       #D97706;
--border:        #E2E8F0;   /* derived */
```

**Semantic colours are reserved.** `--progression` and `--response` mean outcome direction and
nothing else. Never use them for a chart series, a hover state, or a button.

**One accessibility fix required.** Red/green is the worst pair for deuteranopia (~8% of men).
Wherever progression and response appear together — KM curves especially — add a second channel:
solid versus dashed strokes, and direct end-of-line labels rather than a colour legend.

**Cluster palette.** Clusters need their own categorical ramp, distinct from the semantic colours.
Derive *k* hues from the teal→molecular arc so it reads as one family and never collides with
outcome colours.

### Motion

"Dynamic" should mean *the interface shows you what changed*, not decoration. In a clinical tool,
motion that doesn't carry information reads as unserious.

| Event | Motion | Duration |
|---|---|---|
| *k* changes | scatter points tween to new cluster colours and positions | 400ms ease-out |
| *k* changes | KM curves morph between configurations | 400ms, same easing |
| Cluster selected | non-selected points fade to 25% opacity | 200ms |
| Panel first render | staggered fade-up, 60ms between panels | 300ms each |
| Slider drag | dose-response marker tracks live | none — direct manipulation |
| Value updates | numerals count up | 250ms |

Everything honours `prefers-reduced-motion: reduce`. Tweening cluster assignment is the one that
matters — watching a point move between clusters as *k* changes is the whole argument for making
clustering interactive.

No parallax, no autoplay, no decorative particles.

## B1. Patient metadata bar (top)

Full-width, one row, sticky on scroll.

Patient ID (mono) · modalities present as three chips · PAM50 subtype · tumour fraction with
verdict dot · analysis timestamp. Right-aligned: overall state badge (1/2/3).

Missing modalities render as outlined empty chips, not omitted — absence should be visible.

## B2. The 2×2 exploration block

```
┌─────────────────────┬─────────────────────┐
│ Control board       │ Model selection     │
├─────────────────────┼─────────────────────┤
│ Cluster projection  │ Survival curves     │
└─────────────────────┴─────────────────────┘
```

### B2.1 Control board (top-left)

- `k` slider, 2–8, with the pre-registered value marked by a teal tick
- clustering method: GMM (default) / KMeans, radio
- covariance type: full / diagonal / tied
- projection: UMAP / PCA
- reset-to-preregistered button

**When `k ≠ preregistered_k`, an amber `exploratory` badge appears here and simultaneously in the
survival panel.** Coupled state, one visual language.

Recompute is client-side over the cohort payload's latent coordinates — no round trip, so the
tween is smooth.

### B2.2 Model selection (top-right) — replaces the log-rank map

Three small line charts sharing an x-axis of *k*: **BIC** (lower better), **silhouette** (higher
better), **bootstrap stability ARI** (higher better, with the 0.60 gate as a reference line). A
vertical marker on the pre-registered *k*, moving as the user drags the slider.

Footer line: *"k selected from structure. Survival is tested separately."*

This is the panel that replaces the log-rank surface, and the substitution is the point: showing
*p* across every split invites choosing the prettiest one.

### B2.3 Cluster projection (bottom-left)

2D scatter, one point per patient, cluster colour, current patient enlarged with the posterior
uncertainty ring. Convex hulls at 15% opacity per cluster.

Hover → tooltip with ID, cluster, membership probability. Click a cluster → cross-filters B2.4
and B3.

### B2.4 Survival curves (bottom-right)

KM curves per cluster, matching cluster colours, confidence bands at 20% opacity, at-risk table
beneath, OS/PFI toggle.

**Two states.** At the pre-registered *k*: log-rank *p* displayed in mono, with *n* and event
count. At any other *k*: curves render, **the *p*-value does not**, and the amber `exploratory`
badge shows instead.

If A2's gate failed, this panel opens with a persistent line: *"These subgroups differ molecularly
but did not separate survival (p = 0.14). Presented as descriptive."*

## B3. Cluster characteristics

The comparison problem: a tab per cluster makes comparison impossible because you can only see one
at a time.

**Solution: heatmap overview plus detail drawer.**

Rows are features (top ~30 by cross-cluster variance, grouped Pathways / TFs / Genes), columns are
clusters, cells are signed effect size on a diverging teal↔molecular scale. Non-significant cells
(*q* ≥ 0.05) render at 20% opacity so significance is visible without a second encoding.

Row-group toggles collapse Pathways / TFs / Genes independently. Column headers carry cluster
colour and *n*.

Clicking a column opens a right-hand drawer for that cluster: ranked pathway bars, top TFs with
methylation-reliability greying, top genes with log2FC and *q*, and the cluster-versus-normal
summary from A4.

**Why a heatmap.** Comparison across clusters is the actual task, and a matrix is the only layout
where every cluster is visible at once at a glance. The drawer handles depth.

## B4. Drug retrieval

Two columns.

### B4.1 Similar cell lines (left)

Lead line: *"5 cell lines closely resemble this tumour's molecular profile."*

One card per line: name in mono, PAM50 subtype chip, similarity as a small horizontal bar,
key mutations, tissue origin. Selected card drives the right panel.

**On the illustration.** A generic cancer-cell drawing adds no information and risks reading as
decorative in a clinical context. Use instead a small **similarity fingerprint** — a 5-segment
bar showing which molecular axes drove the match. It occupies the same visual slot, gives the card
identity, and carries data. If you want warmth, put it in the card's motion and typography rather
than in stock illustration.

### B4.2 Measured response (right)

Dose-response curves for the selected line: log concentration on x, viability on y, one curve per
drug in the reversal list, Cmax as a vertical marker with the achievable region tinted.

Concentration slider tracks a live readout: *"At 250 nM — palbociclib 41% viability, measured in
MCF7."*

**Label it as measurement, not simulation.** Panel subtitle: *"Measured GDSC dose-response. Not a
simulation."* This panel replaces the ODE and must not inherit its framing.

Above the curves, the reversal candidates from A5.1 — alphabetical, unordered, with the
`threshold_rule` and `validated: false` state surfaced, and the same "order carries no meaning"
line as B5b.

## B5. Retained panels

Sample quality (B1 v2), prognostic interval (B5a v2, with requested and empirical coverage shown
separately and the SCAN-B domain note), glossary affordance, abstention states 1–3.

**Abstention state 3 now suppresses B4 and the prognostic panel.** B2 and B3 still render —
clustering is descriptive and remains legitimate when therapeutic inference is not.

## B6. Component reuse

Existing components map cleanly:

| Existing | Fate |
|---|---|
| `SampleQualityPanel.tsx` | keep, restyle |
| `AbstentionPanel.tsx` | keep, extend suppression list |
| `GlossaryAffordance.tsx` | keep |
| `MolecularStatePanel.tsx` | fold into B3 drawer |
| `ClusterProbabilityChart.tsx` | fold into B2.3 tooltip |
| `RnaUmapPanel.tsx` | becomes B2.3 |
| `PredictionSetPanel.tsx` | **delete** — replaced by B4 |
| `DrugEvidenceTable.tsx` | rework into B4.2 header |
| `PredictorCombinationPanel.tsx` | **delete** — combinations are out with S4 |

New: `ControlBoard`, `ModelSelectionPanel`, `ClusterProjection`, `SurvivalPanel`,
`ClusterHeatmap`, `ClusterDrawer`, `CellLineCard`, `DoseResponsePanel`.

---

# Part C — sequencing

| # | Task | Effort | Blocks |
|---|---|---|---|
| 1 | A1 clustering + model selection | 1 day | everything |
| 2 | A2 survival | 0.5 day | B2.4 |
| 3 | A3 characterisation | 1 day | B3 |
| 4 | A4 normals + signature | 2 days | A5 |
| 5 | A5 retrieval + nearest lines | 2 days | B4 |
| 6 | A6 payloads | 0.5 day | all frontend |
| 7 | Design system, fonts, tokens | 0.5 day | all frontend |
| 8 | B2 block | 3 days | — |
| 9 | B3 heatmap + drawer | 2 days | — |
| 10 | B4 cell lines + curves | 2 days | — |
| 11 | Abstention rewiring | 1 day | — |

Notebooks 1–6 first, in order — the payload contract is what unblocks parallel frontend work.
Roughly **7 days pipeline, 8 days interface**, with items 7–11 parallelisable once A6 lands.

## C1. Open decisions

**If A2 fails** (clusters don't separate survival), the product still works — B2.4 shows curves
without a significance claim and the framing becomes descriptive. Decide now that this is
acceptable, so the temptation to tune *k* never arises.

**If A4's proliferation check fails**, the normal comparison is broken and A5.1's reversal is
meaningless. A5.2's nearest-line panel is independent and still ships.

**Encoder provenance** must land in A6 regardless — the glossary cannot cite an NLL gate for a
model that didn't produce the displayed ellipse.
