# A7 — pre-registration: does the v3 panel transfer to METABRIC?

Written **before** any METABRIC assignment was computed. Everything below is fixed
at this point: the metric, the gene set, the criteria, and what counts as a
failure. Nothing here may be revised after seeing the result. If the test fails it
is reported as a failure, in the manner of A5.1.

## Question

The v3 subgroups were derived on TCGA-BRCA. Do the genes that define them carry
the same structure in an independent cohort measured on a different platform?

## Why this is not "run a METABRIC patient through the panel"

The v3 subgroups are defined on the malignant compartment, after BayesPrism
deconvolution of RSEM counts. METABRIC is Illumina HT-12 microarray and has no
counts; `v3/src/deconv.py` forbids feeding it to BayesPrism. A METABRIC case shown
inside the panel would be computed by a different route and labelled identically,
which is precisely the incomparability this project exists to avoid.

Transfer in **gene space** avoids that. It never re-encodes anything through the
VAE and never claims a METABRIC sample has a malignant-compartment profile.

## Design (fixed)

- **Reference**: TCGA bulk RSEM, `log2(x+1)`, the 1082 patients carrying a
  `gmm:full:k=4` assignment. Bulk, not deconvolved, so the comparison is
  bulk-against-bulk. The deconvolution step is exactly what cannot cross.
- **Genes**: the intersection of the 2247 panel genes with both platforms, after
  symbol harmonisation. Measured coverage before harmonisation: 2140/2247 (95.2%).
- **Scaling**: per-gene z-score computed **within each cohort separately**, so
  platform scale cancels and no cross-cohort normalisation is fitted.
- **Centroids**: per-subgroup mean of the z-scored TCGA profile.
- **Assignment**: each METABRIC sample takes the subgroup of the highest Pearson
  correlation to a centroid. This is the standard PAM50-style calling rule.
- **Subgroup 3 is excluded from scoring in advance.** It has 13 TCGA members. It
  is too small to define a transferable centroid, and its top genes are
  housekeeping (CREG1, ACTG1, HLA-B), which was already identified as a global
  scaling artefact. Its METABRIC count is reported but never scored.

## TCGA reference values (already locked, from the shipped payload)

| Subgroup | n | PAM50 makeup | 
|---|---|---|
| 0 | 530 | LumA 47%, LumB 37%, Her2 14% |
| 1 | 333 | LumA 90% |
| 2 | 206 | Basal 91% |
| 3 | 13 | Normal 64% — not scored |

Overall survival at k=4: log-rank **p = 0.0380**, statistic 8.426, 151 events.

## Criteria

**Primary — subtype concordance.** METABRIC's `CLAUDIN_SUBTYPE` is compared with
TCGA's PAM50 makeup across subgroups 0, 1 and 2. Passes only if **both** hold:

1. The majority subtype agrees for at least 2 of the 3 subgroups.
2. The composition matrices correlate at Pearson r > 0.5, with permutation
   p < 0.05 over 1000 shuffles of the METABRIC assignment.

**Secondary — survival.** Log-rank across the assigned METABRIC subgroups on
overall survival, passing at p < 0.05. Recurrence-free survival is reported
alongside it and labelled secondary. TCGA's k was chosen from BIC and stability
and never from survival, so this is a genuine out-of-sample test.

**Degeneracy guard.** If any single subgroup receives more than 80% of METABRIC
samples, the transfer is declared degenerate and the whole test FAILS, whatever
the other numbers say. A concentrated assignment can produce a good-looking
log-rank while carrying no structure.

**Negative control.** 1000 permutations of the METABRIC assignment. The observed
log-rank statistic must exceed the 95th percentile of that null.

## What a failure would mean

That the subgroups are TCGA-specific — a real and publishable finding for a
research prototype, and the more likely outcome given that the reference is bulk
while the panel was defined on the malignant compartment. It would not
retrospectively invalidate the TCGA result; it would bound its scope.


---

# Outcome (written after running; criteria above unchanged)

## The pre-registered criteria all passed

| Criterion | Result |
|---|---|
| Degeneracy guard | pass — largest subgroup 32.4% of 1980 |
| Majority subtype agrees >= 2/3 | pass — 2/3 |
| Composition r > 0.5 | pass — r = 0.887, permutation p = 0.0010 |
| Overall survival p < 0.05 | pass — p = 3.3e-08, 1143 events |
| Negative control | pass — 37.66 vs null p95 8.20 |

Recurrence-free survival, secondary: p = 1.6e-11, 803 events.

## And the result is nevertheless uninformative

A control added afterwards — not pre-registered, and able only to weaken the
claim — repeated the whole transfer using random gene sets of the same size drawn
from the 15,005 genes outside the panel:

| | Panel | Random sets |
|---|---|---|
| Survival statistic | 37.66 | median **43.30**, 180/200 draws higher (p = 0.90) |
| Composition r | 0.887 | median **0.892**, 72/100 draws higher (p = 0.72) |
| Majority agrees >= 2/3 | yes | **100/100** draws also yes |

Random gene sets do this at least as well as the panel, and on survival they do it
better. The A7 criteria were therefore not discriminative: they measure that bulk
breast expression carries a dominant ER/basal axis which is prognostic and which
any few-thousand-gene centroid recovers. They do not measure whether *this panel*
transfers.

**The honest reading: A7 passed, and A7 does not support the claim it was built to
test.** The fault is in the criteria, which were mine. A pass threshold of
p < 0.05 against a permutation null was far too weak when the alternative
hypothesis should have been a matched random gene set.

One plausible explanation for the panel scoring *below* random on survival: its
genes were selected by one-vs-rest tests on the deconvolved malignant compartment,
so they are tuned to a compartment signal that bulk METABRIC does not carry, while
a generic gene set picks up the bulk ER/proliferation axis unimpeded.

## What would actually be discriminative

Subgroups 0 and 1 are both LumA-majority in TCGA (47% and 90%). Separating them is
not the ER/basal axis, so it is a task a generic gene set should be bad at. Testing
whether the panel distinguishes 0 from 1 in METABRIC better than matched random
sets would be a real test of transfer. That is the experiment to run next, and its
criterion should be "beats matched random gene sets", never "p < 0.05".
