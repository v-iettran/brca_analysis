# Limitations

This document exists so limitations are stated plainly rather than buried in
optimistic wording. If you find a claim in the UI or code that contradicts
this document, that is a bug.

## 1. This is not a diagnostic or treatment-decision tool

Every number here is a research signal derived from public cohort data
(METABRIC, LINCS L1000, GDSC-style cell-line panels, GSE20194/GSE25065). None
of it has undergone the validation (prospective trials, regulatory review)
required to inform an actual clinical decision for any individual patient.

## 2. The Q2+MOFA pCR fusion is explicitly *not* validated — status: blocked

The original plan asked for a refit of
`pCR ~ Q2_regimen_score + MOFA_regimen_reversal` on GSE20194 development, then
unchanged evaluation on GSE20194 validation and GSE25065. This requires a
per-patient MOFA cluster probability for every sample in those two GEO
series, which in turn requires the same raw-GEO-to-gene expression matrix
`scripts/Q5.R` built with live `GEOquery`/platform-annotation packages. Only
the *derived scores* from that original R run were persisted
(`outputs/q5/tables/*_patient_scores.csv`), not the underlying expression
matrix — so there is nothing to compute a MOFA probability from without
re-downloading and re-processing the raw series.

`jobs/refit_pcr_with_mofa.py` checks for the R/Bioconductor prerequisites and
a cached GEO expression matrix at every run; in this environment neither is
available, so it writes an honest **`blocked`** status
(`outputs/q5/tables/q2_mofa_pcr_refit_status.csv`) rather than fabricating a
result. Instructions to unblock it are in that job's docstring.

**What is shown instead:** a genuinely computed **MOFA regimen-reversal
percentile** for any patient we do have full RNA for (all synthetic demo
patients, since they're derived from METABRIC), reported as a clearly
labeled, *separate* discovery signal — never mathematically combined with
the pCR probability.

### For context: a related, but different, historical comparison

The *committed* Q5 tables do contain a comparison of "Q2 regimen signature"
alone vs. "Q2 regimen + Q4 METABRIC signature" (`outputs/q5/tables/patient_external_validation_metrics.csv`):

| Cohort | Split | Model | AUROC |
| --- | --- | --- | --- |
| GSE20194 | validation_100 | Q2 regimen signature | 0.616 |
| GSE20194 | validation_100 | Q2 regimen + Q4 METABRIC signature | 0.727 |
| GSE25065 | external_validation | Q2 regimen signature | 0.594 |
| GSE25065 | external_validation | Q2 regimen + Q4 METABRIC signature | 0.667 |

The combined model looks better here, but "Q4 METABRIC signature" in this
table is the **legacy, population-level BRCA1/2 signature**
(`final-project/brca_target_pipeline.py`), not a per-patient MOFA cluster
score — it cannot be computed for a new single patient at inference time the
way this app needs, and mixing it in would be misleading. We report this
number for transparency, but it is *not* the Q2+MOFA result the plan asked
for, and it is not used anywhere in the live app.

## 3. Only two regimens ever receive a pCR probability

`pipeline_core.pcr_model.REPRESENTED_REGIMENS` only recognizes
5-fluorouracil + doxorubicin + a taxane (paclitaxel or docetaxel) — the
FAC/FEC-taxane regimens Q5.R was actually validated against on GSE20194 and
GSE25065. Any other regimen (including any MOFA-nominated drug) is, and will
remain, a discovery hypothesis with no inferred pCR probability, regardless
of how strong its GCTX reversal or Q2 signature score is.

Even for a represented regimen, a pCR probability is only shown if the
matched cohort's held-out AUROC clears `PCR_APPLICABILITY_GATE_AUROC_MIN`
(0.60) — see the table above; GSE25065's Q2-only AUROC (0.594) is *below*
this gate on its own, though GSE20194 (0.616) is matched first for regimens
that satisfy both cohorts' drug lists.

## 4. The RNA-only cluster classifier is a surrogate, not the MOFA labels themselves

The original MOFA clusters were computed from RNA + copy-number +
methylation jointly. A live patient realistically only has RNA available, so
`pipeline_core.cluster_model` trains/cross-validates an RNA-only classifier
(elastic net, macro-F1 ≈0.76 on 5-fold CV) as a *surrogate* for MOFA cluster
membership. This introduces irreducible extra uncertainty beyond the
classifier's own reported confidence — a "high confidence" prediction is
still a proxy, not a re-derivation of the ground-truth multi-omics cluster.

## 5. GCTX transcriptional reversal is a discovery signal, not therapeutic efficacy

The GCTX/L1000 reversal percentile measures how strongly a compound's
transcriptional signature is anti-correlated with the patient's
cluster-weighted expression signature in cultured cell lines. It says nothing
directly about clinical efficacy, dosing, toxicity, or drug-drug interactions
for this patient.

## 6. Synthetic demo patients are not real patients

The three demo profiles (`jobs/generate_synthetic_patients.py`) are
perturbed, de-identified METABRIC samples, chosen/blended to *illustrate*
high-confidence, mixed-cluster, and low-coverage/abstention scenarios. They
are useful for exercising the pipeline end-to-end, not for any inference
about real-world prevalence of these scenarios.

## 7. Literature and trial evidence is automated and imperfect

- Citation stance (`supporting` / `conflicting` / `neutral` / `unclear`) is
  assigned by a local LLM reading a short excerpt, with a rule-based fallback
  (`pipeline_core.dedup.rule_based_stance`) — always read the excerpt.
- Trial eligibility assessment is a conservative, regex-based read of public
  trial text (HER2/ER/age patterns only) — it is not a substitute for an
  actual eligibility screen and will under-claim ("insufficient information")
  far more often than it over-claims.
- Deduplication is by DOI, then PMID/PMCID, then normalized title/year — near
  duplicates that don't share any of these identifiers may appear twice.

## 8. No prospective or multi-site external validation

Every metric quoted anywhere in this app is retrospective, on public cohort
data the models were also partly developed against (with train/validation
splits, but no truly independent multi-site prospective cohort).

## 9. V2 overlap-nomination limitations (binding)

- **No normal-breast reference.** Cluster signatures are one-vs-rest among
  METABRIC tumours. Reversing a cluster signature moves *away from that
  cluster state*, not necessarily toward a favorable or normal state.
- **RNA UMAP/PCA is a surrogate visualization** colored by MOFA labels, not
  the original multi-omics MOFA coordinate system.
- **Enriched synthetic metadata** (PR, stage, grade, ECOG, organ function,
  location, etc.) may be fictional demo fields; the UI labels provenance.
- **Literature counts** are retrieved relevant references for versioned
  query families — not total publications and not proof.
- **Q2 does not prescribe dosage** and never removes a nomination; it is
  annotation only (percentile, coverage, model reliability).
- **ALMANAC combinations are preclinical** cell-line-aligned priorities
  shown either in the strict overlap lane or the separately labelled
  Predictor comparator lane. They are not clinical recommendations or
  calibrated combination-response scores.
- **Predictor context is not a third nomination list.** Its Q2/Q4 score is
  displayed alongside standard-treatment comparators and never changes
  List 1/List 2 membership or rank. The reference-cohort sensitivity
  percentile and within-patient Predictor rank percentile are distinct.
- **Q4 is correlated evidence.** Because Predictor priorities already contain
  Q4 support, they must not be averaged into the LINCS overlap score; doing so
  would double-count related target/perturbation evidence.
- **Trial matches require investigator confirmation.** Criterion status may
  be `unknown`; potential match only means no known exclusion was found.
- Without the compact breast-cell-line GCTX artifact, List 2 may use a
  residual proxy over committed cluster drug tables — check `source` fields
  in list payloads.

## 8. Human-development labels are snapshots, not suitability

Registry statuses (approved breast/oncology, approved human repurposing,
investigational, tool, withdrawn, unresolved) describe **public compound
development context** at the time the registry was built. They are not:

- patient-specific suitability,
- regulatory advice,
- a reason to promote or bury a raw rank.

Display gating only chooses the default / exploratory / technical lane. Raw
Q4, List 1, and List 2 ranks remain available in technical output.
