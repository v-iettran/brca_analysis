# Clinician guide (V2)

**Research prototype only.** Nothing here should change or justify a clinical
decision. Read [`LIMITATIONS.md`](./LIMITATIONS.md) first.

## Intake

1. **Public hosted demo** — choose one of three synthetic scenarios. Custom
   RNA upload is disabled; the server never accepts or stores expression.
2. **Local scientific mode** — synthetic patients, or upload a normalized RNA
   CSV/TSV (`gene,expression`) with oncology metadata. Backend validation
   remains authoritative.

An analyzing modal shows staged progress. Public mode loads a precomputed
sanitized bundle (no RNA snapshot), so recalculation is disabled.

## What this analysis found

The default clinician view opens with cluster confidence, up to three
default-visible **research nominations**, an evidence rationale (claim-level
links, not hidden chain-of-thought), and the dominant uncertainty. This is
not a treatment ranking.

## Presentation lanes

- **Default-visible** — approved human / breast-or-oncology-context compounds
  with registry provenance.
- **Exploratory** — clinical candidates, collapsed until opened; raw ranks kept.
- **Technical exclusions** — tool/non-drug perturbagens, anonymous `BRD-*` /
  `SA-*` IDs, withdrawn agents, unresolved rows. Raw ranks remain in the
  drawer and in exports.

## Evidence rationale and Copilot

The LLM may only summarize validated run evidence. Every claim must cite an
allowed payload field. Unsafe or ungrounded output is replaced by a
deterministic rationale. Copilot answers include provider/model metadata and
must not invent approval, dosage, or eligibility.

## Left pane toggle

### Patient Analysis

- Expanded oncology profile with **demo-generated** vs **METABRIC-derived** labels.
- Interactive RNA projection (UMAP/PCA surrogate) colored by MOFA cluster, with
  a prominent patient point. This is **not** original multi-omics MOFA space.
- Cluster and residual signature panels ranked by effect size, with optional
  literature counts (retrieved relevant references, not total publications).
- Independent **top up / top down** controls (default 150/150) and
  **Apply and Recalculate** (creates an auditable revision).
- Overlap nomination cards: both-list support, robustness/artifact flags,
  Q2 annotation, ALMANAC combinations when both drugs are overlap nominees,
  literature stance, and evidence tier.
- Standard-treatment comparator cards preserve their actual expression ranks
  and expose a separate Predictor breakdown: reference-cohort Q2 sensitivity,
  Q2 model reliability, Q4 support, integrated priority, and top-quartile
  concordance. Predictor scores never reorder overlap nominations.
- A separate amber Predictor/ALMANAC lane shows eligible standard-treatment
  combinations even when they miss the overlap cutoff. These are preclinical
  context, not additional patient-specific nominations.

### Clinical Trials

- Patient/trial context summary.
- Deduplicated studies aggregated across overlap nominations.
- Criterion-by-criterion `met` / `not_met` / `unknown` with quoted source text.
- A trial is only a **potential match** when no known exclusion is found;
  unknown criteria stay visible. Investigator confirmation is required.

## Persistent Copilot

The right-hand Copilot stays open across views, loads persisted chat history,
and is aware of the active left-side view. It explains structured evidence
only and must not invent approval, dosage, or eligibility.

## Historical Q5 pCR section

Administered-regimen pCR evidence remains available as a **separately labelled
historical validation** section. It is not merged into overlap nomination or
ALMANAC combination scores.
