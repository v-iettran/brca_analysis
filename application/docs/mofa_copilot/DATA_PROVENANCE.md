# Data provenance

Every number in the app traces back to one of these five sources. Nothing is
invented at runtime.

## Artifact inventory: Git vs shared bundle vs generated locally

The copilot reads from two places under the repo root: **committed research
tables** (in Git) and **runtime artifacts** (not in Git). After a fresh
clone you must either copy a shared `copilot_artifacts/` bundle or run the
host-only jobs in `application/jobs/`.

| Location | In Git? | How to obtain | Used for |
| --- | --- | --- | --- |
| `outputs/q2/`, `outputs/q4/mofa_clusters/`, `outputs/q5/tables/` | **Yes** | Comes with clone | Q2 coefficients, MOFA cluster tables, Q5 validation, ALMANAC pairs |
| `outputs/q5/tables/q2_mofa_pcr_refit_status.csv` | **Yes** | Comes with clone | Status of blocked Q2+MOFA pCR refit job |
| `outputs/copilot_artifacts/` (entire folder) | **No** | Shared bundle **or** run jobs below | Classifier, caches, compact GCTX, UMAP, synthetic patients, SQLite DB |
| `outputs/copilot_artifacts/copilot.db` | **No** | Created on first API start if missing | Per-run audit trail and export cache |
| `outputs/copilot_artifacts/exports/` | **No** | Written per analysis run | JSON/CSV/PDF exports (ephemeral) |
| Raw METABRIC (`brca_metabric/`) | **No** | Download from cBioPortal | One-time input to build caches (host-only) |
| Raw GCTX (`level5_beta_trt_cp_*.gctx`, ~33 GB) | **No** | LINCS / local copy | One-time input to `build_compact_gctx_artifact.py` (host-only) |

### Minimum shared bundle (recommended for demo)

Copy into `outputs/copilot_artifacts/`:

| File / folder | ~Size | Job that produces it |
| --- | --- | --- |
| `metabric_expression_cache.parquet` | 380 MB | `train_cluster_classifier.py` |
| `metabric_gene_reference_stats.parquet` | <1 MB | `train_cluster_classifier.py` |
| `cluster_classifier_artifact.json` | <1 MB | `train_cluster_classifier.py` |
| `cluster_classifier_report.md` | <1 MB | `train_cluster_classifier.py` |
| `cluster_rna_centroids.parquet` | ~1 MB | `build_rna_projection_artifacts.py` |
| `rna_umap/` | <1 MB | `build_rna_projection_artifacts.py` |
| `predictor_q2_reference_scores_v1.parquet` | <1 MB | `build_rna_projection_artifacts.py` |
| `synthetic_patients/` | ~1 MB | `generate_synthetic_patients.py` |
| `compact_gctx/` | ~6 GB | `build_compact_gctx_artifact.py` (optional but needed for full List 1/2 overlap) |

Without `compact_gctx/`, the app still runs but overlap nominations use
cluster drug tables and suggestive hypotheses only.

### Build yourself (from `application/` with venv active)

```bash
python3 jobs/train_cluster_classifier.py
python3 jobs/generate_synthetic_patients.py
python3 jobs/build_rna_projection_artifacts.py
# Optional — needs 33 GB GCTX on disk:
# python3 jobs/build_compact_gctx_artifact.py
```

See [`application/README.md`](../../README.md) for prerequisites, secrets, and
Docker notes.

## 1. METABRIC (`final-project/brca_metabric/`)

Public breast-cancer multi-omics cohort (cBioPortal `brca_metabric`). Used
as:

- The **reference population** for z-scoring a new patient's expression
  (`pipeline_core.expression.reference_gene_stats`) — mean/sd per gene across
  ~1,900 METABRIC patients, cached to `outputs/copilot_artifacts/metabric_gene_reference_stats.parquet`.
  This is the same "z-score against cohort" idea `Q5.R` uses, but with a
  persisted population instead of a degenerate n=1 cohort.
- The **training data** for the MOFA cluster labels and the RNA-only
  surrogate classifier (see §3).

Raw METABRIC is read exactly once (to build the caches above); afterwards
neither the API nor Docker runtime touch it again.

## 2. MOFA clusters (`outputs/q4/mofa_clusters/`)

Produced by `final-project/mofa.py` (Multi-Omics Factor Analysis over RNA,
CNA, and methylation) followed by `final-project/mofa_cluster_signatures.py`
(per-cluster PAM50-adjusted differential expression signatures, then LINCS
L1000CDS2 queries for reversing compounds). Files:

- `mofa_clusters.csv` — METABRIC `PATIENT_ID → MOFA_CLUSTER` (5 clusters).
- `cluster_signature.csv` — per-cluster gene coefficients/p-values.
- `cluster_{i}_drug_targets.csv` — per-cluster ranked drug list with
  transcriptional reversal scores (see §4) and annotated targets.

## 3. RNA-only surrogate classifier (`outputs/copilot_artifacts/cluster_classifier_artifact.json`)

Because a real deployment only has RNA (not CNA/methylation) for a new
patient, `jobs/train_cluster_classifier.py` cross-validates two RNA-only
approaches against the MOFA labels in §2:

- **Signature similarity** — cosine similarity to each cluster's top
  differentially-expressed genes.
- **Elastic-net logistic regression** — multinomial elastic net over the
  MOFA-cluster gene signature genes.

Elastic net won on 5-fold CV (macro-F1 ≈0.76 vs ≈0.63 for signature
similarity) and is the persisted, deployed model; both methods' full CV
metrics are in `outputs/copilot_artifacts/cluster_classifier_report.md`.

## 4. GCTX / L1000 drug-reversal evidence (`outputs/q4/mofa_clusters/cluster_{i}_drug_targets.csv`)

The 33 GB `level5_beta_trt_cp_n720216x12328.gctx` LINCS Level-5 file is
**never read at request time**. `jobs/refresh_gctx_cluster_drugs.py` is a
host-only offline job that, for each MOFA cluster's top up/down genes, scores
every compound signature in the GCTX file by weighted connectivity
(reversal = negative correlation with the cluster's up/down signature),
ranks compounds per cluster, and writes the small ranked CSV tables the API
actually reads. `pipeline_core.gctx_evidence` converts `drug_rank` into a
`percentile` (1.0 = strongest reversal) and blends across clusters using the
patient's cluster-probability vector (`blended_drug_evidence`).

### V2 compact GCTX + residual pathway

- Optional compact breast-cell-line HDF5/parquet artifact
  (`jobs/build_compact_gctx_artifact.py`) enables configurable signature-size
  scoring at runtime without mounting the raw 33 GB GCTX.
- List 1 uses committed one-vs-rest MOFA cluster signatures.
- List 2 uses patient residual `z_patient − cluster_centroid` against the
  compact artifact when present, otherwise a residual proxy over cluster
  drug tables (`pipeline_core.gctx_retrieval`).
- RNA projection artifacts live under `outputs/copilot_artifacts/rna_umap/`
  and cluster centroids at `cluster_rna_centroids.parquet`.
- Q5 ALMANAC eligible aligned pairs:
  `outputs/q5/.../q2_almanac_eligible_aligned_pairs.csv` filtered by
  `pipeline_core.almanac_evidence`.

### Parallel Predictor clinical context

`pipeline_core.predictor_evidence` ports the scoring equations from
`scripts/Predictor/predictor_model.R` for standard-treatment context. It uses
the R pipeline's Q2 elastic-net coefficients, Q2 reliability table, Q4
drug-support table, and eligible ALMANAC pairs. Patient Q2 sensitivity is an
empirical percentile against a compact, versioned METABRIC reference-score
artifact (`predictor_q2_reference_scores_v1.parquet`).

The live app reference cohort is METABRIC. The port has equation/input-table
parity with `predictor_model.R`, but it does not claim numerical parity with
committed DLDCCC-reference runs because that external reference expression
matrix is not bundled with the application.

Predictor single-drug and combination priorities are displayed and exported in
a separate comparator lane. They never change List 1/List 2 ranks or membership:
merging the scores would double-count Q4/LINCS-related evidence. Predictor
priorities are relative evidence summaries, not calibrated response
probabilities, clinical recommendations, or dosage guidance.

## 5. Q2 chemotherapy models + Q5 patient validation (`outputs/q2/data/`, `outputs/q5/tables/`)

Elastic-net models trained on cancer cell-line (GDSC/DepMap-style)
chemosensitivity data, predicting sensitivity to individual chemo drugs from
gene expression, with out-of-fold Spearman/Pearson metrics
(`q2_chemotherapy_signature_coefficients.csv`, `q2_chemotherapy_evidence_scores.csv`).
`scripts/Q5.R` re-evaluates these as patient-level regimen scores
(`weighted_signature_score`, ported verbatim into
`pipeline_core.q2_evidence.weighted_signature_score`) against two external
neoadjuvant chemotherapy cohorts with known pCR outcomes (GSE20194,
GSE25065), committing `patient_external_validation_predictions.csv` and
`patient_external_validation_metrics.csv`. `pipeline_core.pcr_model` refits
the Q2-only logistic model in Python and checks it reproduces the committed R
probabilities/AUROC (`q5_parity_report`) before ever displaying a pCR number.

## What is *not* used

- DepMap pan-cancer/BRCA-selective dependency data (`outputs/q4/depmap_*.csv`)
  is kept out of both clinician and technical views per the plan — it is
  exploratory cell-line data, not patient-level evidence.
- The original Q4 BRCA1/2-focused METABRIC signature
  (`final-project/brca_target_pipeline.py`) is **not** mixed into the live
  per-patient pCR model — see [`LIMITATIONS.md`](./LIMITATIONS.md) for why.

## 6. Compound registry (`outputs/compound_registry/v1/`)

Human-development status is a **post-ranking annotation**. `drug_rank`, List 1
percentiles, and List 2 percentiles are never rewritten.

| File | In Git? | Produced by |
| --- | --- | --- |
| `compound_registry.json` / `.parquet` | Generated locally | `jobs/build_compound_registry.py` |
| `lincs_pert_map.json` | Generated locally | same job, from `compoundinfo_beta.txt` when present |
| `manifest.json` | Generated locally | checksums and source versions |
| `review_queue/` | Generated locally | `scan_unresolved_compounds.py`, `propose_compound_reviews.py`, `approve_compound_review.py` |

Sources are a curated seed snapshot plus optional pinned ChEMBL / DrugCentral
extracts. Unknown joins stay `unresolved`. Runtime analysis never contacts
those databases.

Authoritative Q4 generation is `final-project/run_mofa_cluster_q4.py`. The copy
at `person_med_a2/scripts/q4/run_mofa_cluster_q4.py` is deprecated.

## 7. Public demo bundle (`outputs/copilot_artifacts/public_demo_bundle/v1/`)

`jobs/build_public_demo_bundle.py` writes sanitized, expression-free result
payloads for the three synthetic patients. Public mode materializes ephemeral
runs from this bundle instead of loading compact GCTX. The bundle is versioned
against the classifier, registry, and code/artifact manifests. Raw METABRIC,
raw GCTX, compact GCTX, and expression snapshots are excluded.
