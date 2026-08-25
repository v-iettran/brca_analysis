# v3.1 — interface design guide and functionality fixes

**Trigger:** screenshot review of the built v3 interface
**Blocking finding:** the cohort is 87 synthetic samples and 3 real patients
**Scope:** data blocker, then panel-by-panel functional fixes, then the visual system

---

## 0. The blocker — read this before any design work

`cohort_payload.json` contains 90 samples. 87 are `TCGA-SM-####`. Those IDs are generated smoke
data. Only `TCGA-A8-A081`, `TCGA-OK-A5Q2`, and `TCGA-A1-A0SK` are real.

Everything that "looks wrong" in the screenshots is the interface faithfully rendering
synthetic data:

| Symptom | Cause |
|---|---|
| silhouette 0.917, stability 1.000 | generated as separable Gaussian blobs |
| log-rank *p* = 8.1e-68 on 27 events | survival differences built into the generator |
| three perfectly isolated islands in projection | same |
| every pathway at *q* = 0.000 | same |
| `compound_0`, `compound_11`, `compound_15` | placeholder drug names |
| `n_normal = 12`, `n_paired_patients = 0` | synthetic normal reference |

**A1–A4 all logged `passed`.** They passed against data constructed to pass. This is a more
dangerous failure than any of the honest negatives already in the ledger, because it looks like
success — and the gate ledger, which exists to catch exactly this, recorded it as green.

### 0.1 Required fix

Re-run `NB_A1`–`NB_A6` against the real `intrinsic_expression.parquet` from NB02 (n≈200, the same
cohort that produced purity 0.681 and estrogen 0.735). Do not pad to reach a sample count.

### 0.2 Required guard in `_gate.py`

```python
SYNTHETIC_PREFIXES = ("TCGA-SM-", "SYN-", "SMOKE-")

def gate(notebook, name, value, threshold, direction="gte", note="",
         sample_ids=None):
    n_syn = 0
    if sample_ids is not None:
        n_syn = sum(1 for s in sample_ids if str(s).startswith(SYNTHETIC_PREFIXES))
    if n_syn:
        frac = n_syn / len(sample_ids)
        passed = False
        note = f"SYNTHETIC {n_syn}/{len(sample_ids)} ({frac:.0%}) — cannot pass. {note}"
```

Any gate whose input contains generated samples fails, regardless of value. `sample_ids` becomes
a required argument for every gate that consumes a cohort.

### 0.3 Expect the numbers to get worse, and that is correct

On real TCGA data: stability will land nearer 0.6–0.8 than 1.0; silhouette nearer 0.2–0.4 than
0.92; the projection will show overlapping clouds, not islands; and **A2's log-rank may not reach
0.05 at all.** Breast molecular subtypes separate survival weakly, and TCGA-BRCA has ~10% event
rates with short follow-up.

Decide now that a descriptive framing is acceptable, so the temptation to tune *k* never arises
when the real number appears.

---

## 1. Panel-by-panel functional fixes

Every chart in the screenshots is missing axis labels. That is the single largest defect and it
appears in all five panels. Below, per panel, what is broken and what replaces it.

### 1.1 Model selection (top-right)

**Broken:**
- Three sparklines with no y-axis, no x-axis, no tick values. Impossible to read which *k* any
  point corresponds to.
- The purple markers sit at **different x-positions** across the three charts. If all three mark
  *k*=3 they are misaligned; if they mark each metric's own optimum, that contradicts the panel's
  purpose, which is to show one selected *k*.
- BIC is "lower is better" and silhouette is "higher is better", but nothing on screen says so —
  the two charts read as contradictory.
- The dashed line in the ARI chart is the 0.60 gate, unlabeled.

**Replace with a selection table plus one chart.** Three sparklines is the wrong encoding here
because the reader needs to compare *values across k*, which is a lookup task, not a trend task.

```
      k     BIC ↓        Silhouette ↑   Stability ↑    
      2     -203.4       0.61           0.42  ▓▓▓▓░░░░░░
  ▸   3     -351.2       0.92           1.00  ▓▓▓▓▓▓▓▓▓▓   ← selected
      4     -284.6       0.64           0.83  ▓▓▓▓▓▓▓▓░░
      5     -337.9       0.66           0.75  ▓▓▓▓▓▓▓░░░
```

Mono numerals, arrow glyphs in the header stating direction, an inline bar for stability with the
0.60 gate marked, and a caret on the selected row. Below it, one line stating the rule verbatim:
*"Selected: highest stability among k within 10 BIC of the minimum."*

Keep a single small line chart beneath if you want the shape, but with a labeled shared x-axis of
*k* and normalised y so the three series are comparable.

### 1.2 Cluster projection (bottom-left)

**Broken:**
- No axis labels, no legend, no cluster identification.
- The current patient is not visibly distinguished — the spec called for an enlarged point with a
  posterior uncertainty ring.
- Three tiny blobs in the corners of a mostly empty canvas — the view is not fitted to the data.
- The Next.js dev indicator (the dark "N" circle) is visible in the corner. Disable it for demos.

**Fixes:**

**Default to PCA, not UMAP.** UMAP on a few hundred points manufactures separation — it optimises
for local neighbourhood preservation and will render overlapping clusters as tidy islands. Since
you cluster in latent space and then project, tidy islands are partly the projection's doing, and
that is circular evidence. PCA is linear, honest, and its axes carry variance-explained. Label
them `PC1 (34% var)` / `PC2 (19% var)`. Keep UMAP as an option with an inline note that distances
between clusters are not meaningful.

**Legend with counts and identity:** colour swatch · `Subgroup 1` · `n=68` · `PAM50 majority: LumA`.
The PAM50 majority is what converts an arbitrary integer into something a clinician recognises.

**Current patient:** 2× radius, dark stroke, posterior ellipse at 30% opacity, direct text label.

**Fit the viewport** to data bounds with 5% padding. Draw cluster centroids as small crosses.

### 1.3 Survival (bottom-right)

**Broken — and these are reporting defects, not aesthetics.** <cite index="5-1">An incomplete y-axis range or a missing at-risk table is a recognised "missing visual element" in the oncology trial literature.</cite>

- No y-axis. It must run **0 to 1** and be labeled `Overall survival probability`.
- No x-axis label or ticks. Must state the time unit: `Months since diagnosis`.
- Curves start partway across the panel instead of at (0, 1.0).
- The at-risk table's column headers are `0 / 59 / 119` with no indication they are time points,
  and they are not aligned to x-axis ticks.
- Cluster identity is three floating numerals (`0`, `1`, `2`) near the curve ends.
- No censoring marks, no median survival, no confidence bands.

**Rebuild to the standard set:** <cite index="2-1">at-risk table beneath the x-axis at regular intervals, confidence bands, the log-rank p-value, and axis labels specifying the time unit and whether the y-axis shows survival or cumulative incidence.</cite>

- Y from 0 to 1, gridlines at 0.25 intervals, labeled.
- X in months, ticks every 24, at-risk columns aligned to those exact ticks with a `Months` header.
- Direct end-of-line labels: `Subgroup 2 (n=29)` — never a colour-only legend.
- Solid / dashed / dotted stroke per subgroup as a second channel beyond colour.
- Censoring ticks, unless they obscure the curves at your n — <cite index="3-1">the urology reporting guidance notes censoring hash marks can obscure the survival curve and should then be omitted.</cite>
- Median survival per subgroup in a small inline table, or "not reached".
- Header line in mono: `log-rank p = 0.031 · n = 197 · events = 44`.

**When *k* ≠ pre-registered:** curves render, the *p*-value is replaced by the amber `exploratory`
badge. Already spec'd; verify it survives the rebuild.

### 1.4 Cluster characteristics heatmap

**Broken:**
- **No colour scale legend.** The reader cannot tell what dark blue versus light blue means, or
  whether the scale is diverging or sequential.
- The palette is effectively monochrome blue. The spec called for diverging teal ↔ molecular so
  that sign is readable; right now up and down look identical.
- No *q*-value encoding — the 20%-opacity treatment for non-significant cells is absent.
- Feature types are interleaved (`KRT5` gene, `MKI67` gene, `EGFR` pathway, `E2F1` TF) with no
  visual grouping, so the reader cannot tell which rows are comparable.
- Column headers are `c0 / c1 / c2` — no *n*, no PAM50 majority.

**Fixes:**
- **Diverging scale, centred at zero**, teal for down, molecular purple for up, with a legend
  showing `−2 ─ 0 ─ +2` and the unit (`standardised effect size`).
- **Row groups as visual bands** with headers `PATHWAYS (14)` / `TRANSCRIPTION FACTORS (10)` /
  `GENES (30)`, separated by whitespace, each independently collapsible. The existing pill toggles
  stay but grouping must be visible when all three are on.
- Non-significant cells (*q* ≥ 0.05) at 20% opacity.
- Column headers: colour dot · `Subgroup 1` · `n=68` · `LumA`.
- Sort rows by max |effect| **within** group, not globally.
- Row hover → cross-highlight; cell hover → tooltip with effect, *q*, and direction.

**On the drawer:** every pathway showing `q=0.000` is a synthetic-data artifact and should resolve
after §0. Render *q* as `<0.001` rather than `0.000` — a *q* of exactly zero is never true.

### 1.5 Drug retrieval

**Broken:**
- `compound_0`, `compound_11`, `compound_15` — placeholders on screen.
- **The dose-response chart has no axes at all.** No concentration values, no viability scale.
- Concentration slider defaults to minimum, so the readout says `100% viability` for both drugs —
  the least informative possible default.
- Two curves nearly superimposed with no legend distinguishing them.
- The Cmax shaded region is unlabeled.
- The similarity fingerprints drop from full-width (MCF7) to ~5% (BT474, MDAMB231, ZR751), which
  suggests a degenerate similarity metric. Check after §0; if the falloff persists on real data,
  the cosine similarity is saturating and needs re-scaling.

**Fixes:**
- X-axis: log concentration, labeled `Concentration (nM)`, ticks at decades (1, 10, 100, 1000).
- Y-axis: `Cell viability (%)`, 0–100, gridlines at 25.
- IC50 marker per curve with a value label.
- Cmax band labeled with the actual figure: `Plasma Cmax 480 nM`, with the achievable region
  tinted and the unachievable region left plain.
- **Slider defaults to Cmax**, not the minimum. That is the clinically meaningful point.
- Direct curve labels at the right edge, not a legend.
- Readout in mono, stating the source: `At 480 nM — palbociclib 38% viability (GDSC, MCF7)`.

### 1.6 Evidence rationale and patient metadata

**Broken — this panel contains stale v1 text:**
- *"The RNA-only surrogate places the largest probability on MOFA cluster 3"* — there is no MOFA
  and no surrogate in v3. This is copy from the deleted `cluster_model.py` path.
- It says **RNA-only** for `TCGA-A8-A081`, which is your **full-modality** demo patient.
- `100%, high confidence` — a posterior of exactly 1.0 is a synthetic-data artifact.
- Garbled sentence: *"no compound is shown only as evidence, not a recommendation."*
- 8 of 12 metadata fields read `Not recorded`, which makes the panel look broken.

**Fixes:**
- Regenerate all rationale strings from the v3 payload. Grep the frontend for `MOFA`, `surrogate`,
  `cluster_prediction` and remove.
- Derive the modality claim from `modalities_used`, never hardcode.
- Metadata: show populated fields first; collapse empty ones behind `4 fields not recorded`.
  Absence of data should be one quiet line, not eight loud ones.
- Fix the sentence: *"Compounds are shown as evidence, not as recommendations."*

---

## 2. The narrative problem

Each panel is currently an island. A clinician scrolling sees five unrelated widgets. The fix is
structural, not cosmetic: **each panel states what it establishes, and hands off to the next.**

The spine:

> This patient sits in **Subgroup 2** (position, with uncertainty)
> → Subgroup 2 is defined by **elevated estrogen and androgen signalling** (characteristics)
> → Subgroup 2 differs from normal breast tissue in **these genes** (signature)
> → **These compounds** reverse that difference, and **these cell lines** resemble this tumour
>    (retrieval)

Implementation: every panel gets a one-line `takeaway` in its header, generated from the payload
and passed through `assert_safe`.

| Panel | Takeaway line |
|---|---|
| Sample quality | "62% tumour content — sufficient for analysis." |
| Model selection | "The data supports 3 subgroups." |
| Projection | "This patient falls in Subgroup 2 (68% membership)." |
| Survival | "The 3 subgroups differ in overall survival (p = 0.031)." |
| Characteristics | "Subgroup 2 is defined by elevated estrogen and androgen signalling." |
| Retrieval | "5 cell lines resemble this tumour; these compounds reverse its signature." |

Add a persistent left-rail progress indicator with the five steps, current step highlighted,
click to scroll. That is what converts a scroll into a story.

---

## 3. Visual system

The reference design's strengths: generous whitespace, large soft-radius cards, big display
numerals as focal points, layered depth, and restrained accent colour. Its blurred organic shapes
are decorative and should not carry over — in a clinical tool, every visual element should encode
something.

### 3.1 Tokens

```css
--bg:             #F1F5F9;   /* slightly deeper than #F8FAFC — lets cards lift */
--surface:        #FFFFFF;
--surface-sunken: #F8FAFC;   /* chart wells */
--surface-dark:   #0F172A;   /* focal panels only */

--text-primary:   #0F172A;
--text-secondary: #475569;
--text-muted:     #94A3B8;

--clinical-900:   #0C4A6E;   /* blue-shifted per your note */
--clinical-700:   #0369A1;
--clinical-500:   #0EA5E9;
--teal-primary:   #0F766E;
--teal-secondary: #14B8A6;
--molecular:      #7C3AED;

--progression:    #DC2626;
--response:       #16A34A;
--warning:        #D97706;

--border:         #E2E8F0;
--radius-card:    20px;
--radius-inner:   12px;
--shadow-card:    0 1px 3px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.06);
```

**Diverging scale for the heatmap** (this is the one you're missing):
`#0F766E → #5EEAD4 → #F8FAFC → #C4B5FD → #7C3AED`, centred at zero.

**Cluster categorical ramp**, distinct from all semantic colours:
`#0369A1`, `#7C3AED`, `#0F766E`, `#D97706`, `#DB2777`, `#65A30D`, `#0891B2`, `#9333EA`.

**Reserved:** `--progression` and `--response` mean outcome direction only. Never a series colour,
never a hover state, never a button.

### 3.2 Typography

IBM Plex Sans for prose, **IBM Plex Mono for every numeral** — *p*-values, concentrations,
patient IDs, counts, axis ticks. Enable `font-variant-numeric: tabular-nums` so columns align and
values don't jitter during transitions.

Scale: 11 (axis ticks) / 12 (captions) / 13 (labels) / 14 (body) / 16 (panel title) /
20 (section) / 32 (display numerals). Weights 400 / 500 / 600.

**Display numerals are the reference design's best idea.** One per panel, large: tumour fraction,
subgroup count, log-rank *p*, cell-line count. It gives each panel a focal point and makes the
page scannable.

### 3.3 Card anatomy

```
┌────────────────────────────────────────┐
│ EYEBROW (11px, 500, muted, tracked)    │
│ Panel title (16px, 600)          [⋯]   │
│ Takeaway line (13px, secondary)        │
│ ┌────────────────────────────────────┐ │
│ │ chart well — surface-sunken,       │ │
│ │ radius-inner, 16px inset           │ │
│ └────────────────────────────────────┘ │
│ Footnote / provenance (12px, muted)    │
└────────────────────────────────────────┘
```

24px padding, `--radius-card`, `--shadow-card`. Charts sit in a sunken well — this is what gives
the reference design its depth without decoration.

### 3.4 Motion

| Event | Motion | Duration |
|---|---|---|
| *k* changes | points tween position and colour | 400ms ease-out |
| *k* changes | KM curves morph | 400ms, matched |
| Cluster selected | others fade to 25% | 200ms |
| Panel enter | fade-up, 60ms stagger | 300ms |
| Display numerals | count up | 250ms |
| Slider drag | direct tracking | 0 |

`prefers-reduced-motion: reduce` disables all of it. No parallax, no autoplay, no floating shapes.

### 3.5 Chart rules — apply to every chart, no exceptions

1. Both axes labeled, with units.
2. Y-axis starts at zero for proportions and probabilities.
3. Direct labels on series; a colour-only legend is a last resort.
4. Colour is never the sole channel — pair with stroke style or position.
5. Tick values in mono.
6. Every chart states its *n*.
7. Every chart states its source (`GDSC`, `TCGA-BRCA`, `LINCS`).

Rule 1 alone fixes most of what's wrong in the screenshots.

---

## 4. Sequencing

| # | Task | Effort | Note |
|---|---|---|---|
| 1 | Gate guard for synthetic IDs | 0.5 day | prevents recurrence |
| 2 | Re-run A1–A6 on real n≈200 | 1 day | **blocks everything** |
| 3 | Purge stale v1 strings (MOFA, surrogate) | 0.5 day | independent |
| 4 | Chart primitives: axes, legends, labels | 2 days | shared by all panels |
| 5 | Survival panel to CONSORT standard | 1 day | largest single defect |
| 6 | Model selection → table | 0.5 day | |
| 7 | Projection: PCA default, legend, patient | 1 day | |
| 8 | Heatmap: diverging scale, legend, groups | 1 day | |
| 9 | Dose-response axes, Cmax default | 1 day | |
| 10 | Takeaway lines + progress rail | 1 day | the narrative fix |
| 11 | Visual system tokens and card anatomy | 1.5 days | |

Items 1–3 first. Item 4 before 5–9, since a shared axis/legend/label primitive is what stops this
class of defect recurring — building each chart's axes ad hoc is how five panels ended up with
none.

Item 10 is what turns five widgets into the coherent story you're asking for, and it is cheap.

## 5. Expect a harder conversation after §0

When A1–A6 re-run on real data, the clusters will overlap, the silhouette will drop, and A2 may
miss 0.05. The interface must be able to say so. Specifically:

- The survival panel needs its **descriptive framing** state built, not just designed — *"These
  subgroups differ molecularly but did not separate survival (p = 0.14)."*
- The projection needs to look right with **overlapping clouds**, which is the normal case, not
  islands.
- The heatmap needs to handle **mostly non-significant cells** gracefully; at 20% opacity, a sparse
  matrix should still read as informative rather than empty.

Design for the real result, not the synthetic one.
