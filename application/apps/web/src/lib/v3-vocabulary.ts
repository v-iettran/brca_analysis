/**
 * Machine identifiers to human descriptions.
 *
 * Payload fields carry snake_case keys because they are provenance records, not
 * prose. Printing `gdsc_measured_hill` on screen leaks the schema at the reader
 * and says nothing about what was actually done, so every identifier that
 * reaches the interface is translated here — with a short label for inline use
 * and a full sentence for tooltips and glossaries.
 */

export type Term = { label: string; detail: string };

const TERMS: Record<string, Term> = {
  // Curve and assay provenance
  gdsc_measured_hill: {
    label: "GDSC2, fitted Hill curve",
    detail:
      "A Hill curve fitted by GDSC to measured viability readings for this cell line and drug. The curve is a fit to real measurements, not a simulation.",
  },
  display_band_8pct: {
    label: "±8% display band",
    detail:
      "A fixed ±8% ribbon drawn to make the curve readable. It is not a confidence interval and carries no statistical meaning.",
  },

  // Retrieval sources
  lincs_breast_trt_cp: {
    label: "LINCS breast compound perturbations",
    detail:
      "Level-5 LINCS signatures for small-molecule treatments in eight breast cell lines, filtered to exemplar signatures that pass QC. Scores are the median reversal across a compound's signatures.",
  },
  depmap_breast_expression: {
    label: "DepMap breast expression",
    detail:
      "Bulk mRNA expression for DepMap breast cancer cell lines, projected into a PCA shared with this tumour cohort.",
  },
  depmap_model_csv: {
    label: "DepMap model annotation",
    detail: "Cell-line metadata from DepMap's model table: receptor status, subtype, and origin.",
  },
  connectivity_reversal_top_n: {
    label: "top-N connectivity reversal",
    detail:
      "Compounds whose expression signature is most anti-correlated with this subgroup's difference from normal tissue. Unvalidated: a high score is a hypothesis, not evidence of effect.",
  },
  shared_peak_across_retrieved_lines: {
    label: "scaled across retrieved lines",
    detail:
      "Fingerprint bars are divided by the largest contribution seen across all retrieved lines, so bars can be compared between cards.",
  },

  // Cohort and encoder provenance
  pca_intrinsic_expression: {
    label: "PCA of intrinsic expression",
    detail:
      "Positions come from a PCA of the deconvolved tumour-intrinsic gene set. The committed PoE-VAE was fitted on METABRIC and does not cover this cohort, so it is not used here.",
  },
  tcga_brca_intrinsic_expression: {
    label: "TCGA-BRCA intrinsic expression",
    detail: "Tumour-intrinsic expression for the full TCGA-BRCA cohort, after deconvolution.",
  },
  tcga_sample_type_11: {
    label: "TCGA adjacent normal tissue",
    detail:
      "Normal breast tissue taken adjacent to a tumour, identified by TCGA sample type 11. These are few, and can carry field effects from the neighbouring tumour.",
  },
  intrinsic_epithelium_vs_normal_epithelium: {
    label: "epithelium compared to epithelium",
    detail:
      "Tumour epithelium is compared against normal epithelium rather than bulk against bulk, so the difference is not just a change in tissue composition.",
  },
  stability_within_10_bic: {
    label: "most stable k within 10 BIC of the minimum",
    detail:
      "Among values of k whose BIC is within 10 of the best, the one with the highest bootstrap stability is chosen. None of these criteria uses survival.",
  },

  // Roles and states
  her2_amplified: { label: "HER2-amplified", detail: "The subgroup with the highest mean ERBB2 expression." },
  er_high: { label: "ER-high", detail: "The subgroup with the highest mean ESR1 expression." },
  basal_enriched: {
    label: "basal-enriched",
    detail: "The subgroup with the highest mean proliferation signal.",
  },
  full_modality: { label: "all assays present", detail: "RNA, copy number and methylation are all available." },
  missing_view: { label: "an assay is missing", detail: "At least one assay is unavailable, so the position is less certain." },
  abstain: { label: "abstained", detail: "Therapeutic inference is withheld for this sample." },
  posterior_width: {
    label: "uncertain subgroup assignment",
    detail: "The spread of the subgroup membership probability exceeded the abstention threshold.",
  },

  // Sections
  sample_quality: { label: "sample quality", detail: "Tumour content and cell-type composition." },
  cluster_projection: { label: "cluster projection", detail: "Where this tumour sits among the cohort." },
  cluster_characteristics: { label: "cluster characteristics", detail: "What defines each subgroup." },
  drug_retrieval: { label: "drug retrieval", detail: "Similar cell lines and their measured responses." },
  prognostic_estimate: { label: "prognostic estimate", detail: "A conformal survival interval." },
};

export function term(key: string | null | undefined): Term {
  if (!key) return { label: "not recorded", detail: "" };
  const found = TERMS[key];
  if (found) return found;
  // Unknown identifiers still should not show as snake_case.
  return { label: key.replace(/_/g, " "), detail: "" };
}

export function termLabel(key: string | null | undefined): string {
  return term(key).label;
}

export function termDetail(key: string | null | undefined): string {
  return term(key).detail;
}
