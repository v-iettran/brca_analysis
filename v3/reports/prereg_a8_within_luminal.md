# A8 — pre-registration: does the panel separate the two luminal subgroups?

Written before anything was computed. A7 passed its criteria and taught us nothing,
because a matched random gene set passed them too. A8 exists to be discriminative,
so its criterion is comparative from the start.

## Why this task

TCGA subgroups 0 and 1 are both LumA-majority:

| | n | PAM50 makeup | proliferation |
|---|---|---|---|
| 0 | 530 | LumA 47%, LumB 37%, Her2 14% | +0.211 |
| 1 | 333 | LumA 90% | −0.578 |

Telling them apart is a **within-luminal** distinction — proliferation, not the
ER/basal axis. That matters because the ER/basal axis is what any few-thousand-gene
set recovers, which is exactly why A7 was uninformative. A generic gene set should
be comparatively poor at this task. If the panel is not, it carries no subgroup
information beyond the obvious axis.

## Procedure (fixed)

Identical transfer to A7: TCGA bulk `log2(x+1)`, per-gene z-score within each
cohort, centroids per subgroup, Pearson correlation. The only new quantity is a
signed axis score for each METABRIC sample:

    score = corr(sample, centroid_0) − corr(sample, centroid_1)

Higher means more like subgroup 0, the proliferative luminal one.

**Anchor.** METABRIC's own `CLAUDIN_SUBTYPE` calls, which are independent of
anything we computed. Restricted to samples METABRIC calls LumA or LumB. The panel
score should rank LumB above LumA.

**Null.** 200 random gene sets of the same size, drawn from the 15,005 genes
outside the panel and **matched to the panel's decile profile of mean TCGA
expression**. A7's null was unmatched; if panel genes are simply better measured,
an unmatched null would hand us a win that means nothing.

## Criteria

**Primary.** Panel AUROC for LumB-versus-LumA must exceed the 95th percentile of
the matched random sets — empirical p ≤ 0.05. A raw AUROC value, however high, is
not a pass on its own. This is the lesson of A7 and it is not negotiable here.

**Secondary.** Among the same luminal samples, split by the sign of the axis score
and test overall survival by log-rank. Judged the same comparative way: the
statistic must beat the matched random sets. Reported either way.

**Reported regardless.** Panel AUROC, the random distribution, and how many random
sets beat the panel — whatever the direction.

## What each outcome means

- **Panel beats matched random**: the panel carries within-luminal subgroup
  information that survives a platform change. A7's null result would then be
  about the criteria, not the panel.
- **Panel does not beat matched random**: taken with A7, the subgroups are a
  restatement of the ER/proliferation axis plus TCGA-specific structure, and the
  panel does not transfer. That is a legitimate finding and would be reported as
  the headline, not a footnote.


---

# Outcome (written after running; criteria above unchanged)

## Primary passed, then did not survive a stricter null

| | Panel | Matched random (mean only) |
|---|---|---|
| AUROC LumB vs LumA | **0.8774** | median 0.8657, max 0.8766 — 0/200 beat it, p = 0.005 |

The pre-registered criterion was met. The margin is 0.012 AUROC.

Panel genes are much more variable than the pool (sd 1.176 vs 0.946) and much more
highly expressed (mean 10.65 vs 6.16), and A8's null matched only the mean. A
second null matching **mean and standard deviation**:

| | Panel | Matched random (mean + sd) |
|---|---|---|
| AUROC LumB vs LumA | 0.8774 | median **0.8764**, max 0.8843 — **89/200 beat it, p = 0.45** |

The edge was gene variance, not subgroup information.

## Secondary failed outright

Within-luminal overall survival, split by the axis sign: panel statistic 29.40
against a matched-random median of 33.17, with 161/200 random sets scoring higher
(p = 0.81). Random gene sets separate survival better than the panel does.

## Conclusion across A7 and A8

**The v3 gene panel does not transfer to METABRIC beyond what any comparably
expressed, comparably variable gene set achieves.** Three independent comparisons
agree: A7 survival (random better), A7 subtype concordance (random equal), A8
within-luminal discrimination (random equal once variance is matched), A8
within-luminal survival (random better).

What this does and does not say:

- It does **not** say the TCGA subgroups are wrong within TCGA. Their internal
  statistics are unchanged.
- It says the part of the panel that crosses to another platform in bulk space is
  the generic expression axis, and the subgroup-specific part does not survive.
- One confound cannot be removed with this data: the TCGA subgroups are defined on
  the deconvolved malignant compartment, while the transfer is necessarily bulk.
  METABRIC has no counts and cannot be deconvolved, so "would these subgroups
  replicate in a deconvolved METABRIC" is unanswerable here. The negative result
  is about bulk transfer, which is the only transfer available.

A caveat on the stricter null: 4 of its 16 mean/sd strata were under-supplied in
the non-panel pool, so matched draws are marginally smaller than the panel. The
result is not close enough for that to change the direction.
