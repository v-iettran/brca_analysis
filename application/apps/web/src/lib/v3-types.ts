export const V3_SCHEMA = "v3_cluster" as const;

/** Curated development status for a compound. Never inferred. */
export type EvidenceTier = "standard_of_care" | "investigational" | "not_human" | "unresolved";

/** Curated breast-cancer evidence for a feature. Never inferred from this cohort. */
export type FeatureTier = "established" | "investigational" | "not_established";

export interface V3Preregistered {
  k: number | null;
  timestamp: string;
  selection_rule: string;
  method: string;
  covariance_type: string | null;
  bic?: number | null;
  silhouette?: number | null;
  stability?: number | null;
  clustering_available: boolean;
  stability_threshold: number;
}

export interface V3KmCurve {
  time: number[];
  survival: number[];
  lower: number[];
  upper: number[];
  at_risk: number[];
  events?: number[];
  median?: number | null;
  n?: number;
  n_events?: number;
  cluster?: number;
}

export interface V3KmBlock {
  curves: Record<string, V3KmCurve>;
  p_value?: number | null;
  statistic?: number | null;
  n?: number;
  n_events?: number;
  exploratory: boolean;
}

export interface V3Configuration {
  method: string;
  covariance_type: string | null;
  k: number;
  exploratory: boolean;
  assignments: Record<string, number>;
  membership: Record<string, number[]>;
  km: { os: V3KmBlock; pfi: V3KmBlock };
}

export interface V3ComparisonMatrix {
  features: string[];
  families: string[];
  clusters: number[];
  effects: number[][];
  q: number[][];
}

export interface V3ClusterAnnotation {
  cluster: number;
  n: number;
  esr1_mean: number;
  erbb2_mean: number;
  prolif_mean: number;
  pam50_majority?: string | null;
  er_high?: boolean;
  her2_amplified?: boolean;
  basal_enriched?: boolean;
}

export interface V3CohortPayload {
  schema_version: typeof V3_SCHEMA;
  encoder: string;
  clustering_available: boolean;
  preregistered: V3Preregistered;
  model_selection: Array<{ k: number; bic: number; silhouette: number; stability: number }>;
  gates: {
    a1: { passed: boolean; clustering_available?: boolean; stability?: number };
    a2: { passed: boolean; p_os?: number | null; p_pfi?: number | null; framing: "prognostic" | "descriptive" };
    a3?: { passed: boolean; per_cluster_pathway_counts?: Record<string, number> };
    a4: { passed: boolean; reversal_available?: boolean; caveats?: string[] };
    a5?: Record<string, unknown>;
  };
  projections: { umap: Record<string, number[]>; pca: Record<string, number[]> };
  posterior_width?: Record<string, number>;
  configurations: Record<string, V3Configuration>;
  cluster_profiles: Array<Record<string, unknown>>;
  comparison_matrix: V3ComparisonMatrix;
  cluster_annotations: Record<string, V3ClusterAnnotation>;
  tf_reliability?: Array<{ tf: string; reliability: string; reliability_reason?: string; source?: string }>;
  survival_sensitivity?: Array<{
    k: number;
    p_value: number;
    statistic?: number;
    q_value?: number;
    exploratory?: boolean;
  }>;
  pam50?: Record<string, string>;
  analysis_timestamp?: string;
  takeaways?: Record<string, string>;
  n_samples?: number;
  cohort_source?: string;
  synthetic_samples?: number;
  projection_meta?: {
    default?: "pca" | "umap";
    pca_variance_ratio?: number[];
    umap_available?: boolean;
    umap_note?: string;
  };
  fingerprint_axes?: V3FingerprintAxis[];
  joint_projection?: {
    axes: number[];
    variance_ratio: number[];
    note?: string;
    tumours: number[][];
    patients: Record<string, number[]>;
    lines: Record<string, number[]>;
  };
  evidence_reference?: {
    schema: string;
    curated_date: string;
    tiers: Record<string, string>;
    caveat: string;
  };
  evidence_tier_labels?: Record<string, string>;
  reversal_by_cluster?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
}

export interface V3DoseCurve {
  drug: string;
  canonical?: string;
  line_id: string;
  concentration_nm: number[];
  viability: number[];
  /** Fixed +/-8% display band, not a fitted confidence interval. */
  band_lower?: number[];
  band_upper?: number[];
  band_kind?: string;
  ic50_nm: number;
  cmax_nm?: number | null;
  /** The concentrations GDSC actually tested. */
  min_conc_nm?: number | null;
  max_conc_nm?: number | null;
  /** True when the fitted IC50 lies outside the tested range. */
  ic50_extrapolated?: boolean;
  auc?: number | null;
  z_score?: number | null;
  rmse?: number | null;
  evidence_tier?: EvidenceTier;
  evidence_label?: string;
  evidence_reason?: string;
  retrieved?: boolean;
  source: string;
  measured: boolean;
  simulation: boolean;
}

export interface V3MarkerComparison {
  marker: string;
  line: number;
  subgroup: number;
}

export interface V3CellLine {
  line_id: string;
  name: string;
  /** Cosine similarity in joint PCA space, range [-1, 1]. Not a percentage. */
  similarity: number;
  rank: number;
  pam50?: string | null;
  /** Whether this line's PAM50 call matches the patient's. */
  pam50_match?: boolean | null;
  tissue?: string;
  mutations?: string[];
  subtype_features?: string | null;
  oncotree_subtype?: string | null;
  primary_or_metastasis?: string | null;
  fingerprint: number[];
  fingerprint_scale?: string;
  marker_comparison?: V3MarkerComparison[];
  curves?: V3DoseCurve[];
}

/** What each fingerprint axis means: variance share and strongest loadings. */
export interface V3FingerprintAxis {
  component: number;
  variance_ratio: number;
  top_positive: string[];
  top_negative: string[];
}

export interface V3PatientPayload {
  schema_version: typeof V3_SCHEMA;
  patient_id: string;
  role: string;
  title?: string | null;
  description?: string | null;
  encoder: string;
  state: number;
  banner?: string | null;
  modalities_present: string[];
  pam50?: string | null;
  analysis_timestamp?: string;
  patient_metadata: Record<string, unknown>;
  sample_quality: import("./types").SampleQuality;
  position: {
    umap_coords: number[];
    pca_coords?: number[];
    posterior_width: number;
    cluster: { label: number; posterior_mass: number };
    membership: number[];
  };
  abstention: import("./types").AbstentionState;
  prognostic_estimate?: import("./types").PrognosticEstimate | null;
  reversal_candidates?: {
    members: Array<{
      drug: string;
      canonical?: string;
      reversal_score?: number;
      n_signatures?: number;
      rank?: number;
      source?: string;
      validated?: boolean;
      evidence_tier?: EvidenceTier;
      evidence_label?: string;
      evidence_reason?: string;
      max_phase?: string | null;
      approved_indication?: string | null;
      target?: string | null;
      moa?: string | null;
    }>;
    validated: boolean;
    threshold_rule: string;
    order_carries_no_meaning: boolean;
    source: string;
  } | null;
  nearest_lines?: V3CellLine[] | null;
  limitations: string[];
  s4_ships: boolean;
  takeaways?: Record<string, string>;
  modalities_used?: string[];
}

export function configId(method: string, covariance: string | null, k: number): string {
  return method === "gmm" ? `gmm:${covariance}:k=${k}` : `kmeans:na:k=${k}`;
}
