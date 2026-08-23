# SCAN-B access request (do this on day one)

SCAN-B (Sweden) RNA-seq + treatment + outcome is the best validation asset
in the v2 plan (NB13). Access is **not** immediate — apply at the start of
the project and keep this file as the paper trail.

## Dataset

- GEO series: **GSE96058** (and related SCAN-B accessions)
- What we need: bulk RNA-seq, treatment annotation, survival / pCR if available
- Why: conformal fusion labels (implementation spec §7.2)

## Request checklist

1. Create a GEO / NCBI account if needed.
2. Open https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96058
3. Follow any "controlled access" or dbGaP / EGA pointers listed on the series.
4. If the series page points to the SCAN-B data access committee, submit:
   - requester name and institution
   - project title: "Multi-omic latent state to mechanistic drug-response simulation in breast cancer (research prototype, not CDS)"
   - intended use: held-out conformal calibration of in-silico drug ranking
   - confirmation that no attempt will be made to re-identify patients
5. Record the request date, ticket / email, and expected turnaround below.

## Local log

| Date | Action | Result |
|------|--------|--------|
| 2026-08-21 | Checklist created in-repo | pending user submission |

## Fallback if access has not arrived by NB13

Run hierarchical / conformal fusion on:

- TCGA-BRCA survival (downloaded in NB00)
- GSE20194 / GSE25065 neoadjuvant pCR cohorts

Same notebook interface, wider intervals. Swap SCAN-B in when the files land
and re-run the coverage gate.
