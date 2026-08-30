export interface PatientMetadata {
  age_at_diagnosis?: number | null;
  er_status?: string | null;
  her2_status?: string | null;
  pr_status?: string | null;
  claudin_subtype?: string | null;
  histological_subtype?: string | null;
  lymph_nodes_positive?: number | null;
  menopausal_state?: string | null;
  nottingham_prognostic_index?: number | null;
  tumor_stage?: string | null;
  tumor_grade?: number | null;
  tumor_size_mm?: number | null;
  ecog_status?: number | null;
  prior_therapy?: string | null;
  organ_function?: Record<string, unknown> | null;
  location?: Record<string, unknown> | null;
  field_provenance?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface SyntheticPatientSummary {
  synthetic_id: string;
  scenario: "high_confidence" | "mixed_cluster" | "low_quality";
  description: string;
  metadata: PatientMetadata;
  administered_regimen: string[];
}

export interface SyntheticPatientFull extends SyntheticPatientSummary {
  expression: Record<string, number>;
}

export interface ClusterPrediction {
  probabilities: Record<string, number>;
  top_cluster: number;
  top_probability: number;
  confidence_level: "high" | "moderate" | "low" | "abstain";
  gene_coverage: number;
  genes_found: number;
  genes_requested: number;
  method_used: "signature_similarity" | "elastic_net";
  warnings: string[];
}

export interface ClusterGene {
  gene: string;
  coefficient: number;
  p_value: number;
  fdr: number;
  direction: "higher" | "lower";
}

export interface ClusterDetail {
  cluster_id: number;
  patient_probability: number;
  n_in_cluster: number;
  n_out_cluster: number;
  genes_tested: number;
  significant_gene_count: number;
  coefficient_interpretation: string;
  positive_genes: ClusterGene[];
  negative_genes: ClusterGene[];
}

export interface ApplicabilityGate {
  represented: boolean;
  gate_passed: boolean;
  reason?: string | null;
  regimen_label?: string | null;
  validated_cohort?: string | null;
  validated_split?: string | null;
  held_out_auroc?: number | null;
  gate_threshold?: number | null;
}

export interface SupportedPcrResult {
  applicability_gate: ApplicabilityGate;
  mofa_regimen_reversal_percentile: number | null;
  mofa_regimen_reversal_note: string;
  pcr_probability: number | null;
  q2_regimen_score: {
    regimen_score: number | null;
    drugs_requested: string[];
    drugs_scored: string[];
    per_drug?: Record<string, { raw_score: number; z_score: number; genes_used: number }>;
    reason?: string;
  } | null;
}

export interface GctxClusterEvidence {
  cluster_id: number;
  cluster_probability: number;
  drug_rank: number;
  reversal_score: number;
  percentile: number;
  n_signatures: number | null;
  targets: string[];
  n_drugs_in_cluster: number;
}

export interface GctxDrugEvidence {
  drug: string;
  blended_percentile: number | null;
  clusters_with_data: number;
  per_cluster: GctxClusterEvidence[];
}

export interface Q2DrugEvidence {
  drug: string;
  raw_score: number | null;
  z_score: number | null;
  genes_used: number;
  evidence_category?: string | null;
  model_support?: number | null;
  model_spearman?: number | null;
  external_spearman?: number | null;
}

export interface DrugCandidate {
  drug: string;
  targets: string[];
  gctx_evidence: GctxDrugEvidence | null;
  q2_evidence: Q2DrugEvidence | null;
  literature_summary: LiteratureSummary | null;
  is_in_administered_regimen: boolean;
  evidence_tier?: string | null;
  list1_percentile?: number | null;
  list2_percentile?: number | null;
  indication_bucket?: string | null;
  robustness?: RobustnessFlags | null;
}

export interface WarningOut {
  severity: "info" | "caution" | "abstain";
  message: string;
}

export interface SignatureGene {
  gene: string;
  effect: number;
  direction: "up" | "down";
  pval?: number | null;
  fdr?: number | null;
  literature_count?: number | null;
}

export interface SignaturePanel {
  kind: "cluster" | "residual";
  cluster_id: number;
  top_up: number;
  top_down: number;
  n_up: number;
  n_down: number;
  genes: SignatureGene[];
  coverage_fraction?: number | null;
  genes_used?: number | null;
  warnings?: string[];
}

export interface RnaProjection {
  method: string;
  label: string;
  patient: { x: number; y: number };
  reference: Array<{ sample_id: string; x: number; y: number; mofa_cluster: number }>;
  n_reference_total?: number | null;
  n_reference_shown?: number | null;
  genes_used?: number | null;
  gene_coverage?: number | null;
}

export interface RobustnessFlags {
  low_coverage?: boolean;
  single_cell_line?: boolean;
  low_consistency?: boolean;
  weak_dual_support?: boolean;
  generic_stress_pattern?: boolean;
  missing_target_pathway_support?: boolean;
  likely_artifact?: boolean;
  notes?: string[];
}

export interface LiteratureSummary {
  retrieved_relevant_references?: number;
  stance_counts?: Record<string, number>;
  dominant_stance?: string | null;
  note?: string;
  unavailable_reason?: string;
  cache_hit?: boolean;
  top_citations?: CitationOut[];
}

export interface OverlapNomination {
  drug: string;
  canonical: string;
  list1_percentile?: number | null;
  list2_percentile?: number | null;
  weaker_percentile?: number | null;
  stronger_percentile?: number | null;
  rank_product?: number | null;
  list1_rank?: number | null;
  list2_rank?: number | null;
  targets: string[];
  evidence_tier?: string | null;
  indication_bucket?: string | null;
  robustness?: RobustnessFlags | null;
  q2_annotation?: Record<string, unknown> | null;
  literature_summary?: LiteratureSummary | null;
  is_in_administered_regimen?: boolean;
  nomination_rank?: number | null;
  support_class?: "breast_cell_line_supported" | "suggestive" | "excluded_low_confidence" | null;
  support_rank?: number | null;
  human_development_status?: string | null;
  human_development_label?: string | null;
  entity_type?: string | null;
  display_action?: "default_visible" | "exploratory_only" | "technical_excluded" | null;
  display_gate_reason?: string | null;
  registry_match_key?: string | null;
}

export interface ClinicalComparator {
  drug: string;
  canonical: string;
  category: string;
  clinical_context: string;
  list1_rank: number | null;
  list2_rank: number | null;
  list1_percentile: number | null;
  list2_percentile: number | null;
  dual_support_percentile: number | null;
  present_in_both_lists: boolean;
  list1_source: "patient_cluster_compact_gctx" | "mofa_cluster_reference_gctx";
  list2_source: "patient_residual_compact_gctx" | null;
  targets: string[];
  interpretation: string;
  predictor_evidence?: PredictorDrugEvidence | null;
  evidence_concordance?: "concordant_high" | "expression_only" | "predictor_only" | "low_or_uncertain";
}

export interface PredictorDrugEvidence {
  drug: string;
  canonical: string;
  treatment_class: string;
  q2_raw_sensitivity_score: number | null;
  reference_cohort_sensitivity_percentile: number | null;
  q2_model_reliability: number;
  q2_model_spearman: number | null;
  q2_external_spearman: number | null;
  q2_evidence_category: string | null;
  q4_target_support: number | null;
  q4_compound_support: number | null;
  q4_drug_support: number;
  q4_targets_used: string[];
  q4_targets_matched: string[];
  integrated_single_drug_priority: number | null;
  signature_genes_used: number;
  signature_genes_total: number;
  gene_coverage: number;
  within_patient_predictor_rank: number | null;
  within_patient_predictor_percentile: number | null;
  predictor_version: string;
  reference_cohort: "METABRIC";
  parity_scope: string;
  interpretation: string;
}

export interface PredictorCombination {
  drug_a: string;
  drug_b: string;
  combination: string;
  component_drug_priority: number;
  drug_a_priority: number;
  drug_b_priority: number;
  aligned_pair_support: number;
  pair_q4_support: number;
  integrated_combination_priority: number;
  aligned_cell_lines: number;
  aligned_cell_line_names?: string | null;
  cell_line_alignment_confidence?: string | null;
  predictor_version: string;
  interpretation: string;
  rank: number;
}

export interface AlmanacCombination {
  drug_a: string;
  drug_b: string;
  combination: string;
  aligned_cell_lines: number;
  aligned_cell_line_names?: string | null;
  aligned_median_almanac_combo_score?: number | null;
  aligned_pair_support?: number | null;
  component_support?: number | null;
  q2_percentile_a?: number | null;
  q2_percentile_b?: number | null;
  combination_priority?: number | null;
  cell_line_alignment_confidence?: string | null;
  interpretation?: string | null;
  rank?: number | null;
}

export interface AnalysisStage {
  stage_id: string;
  label: string;
  status: "running" | "completed" | "failed";
  detail?: string | null;
  created_at?: string | null;
}

export interface AnalysisProgress {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  current_stage?: string | null;
  stages: AnalysisStage[];
  error_message?: string | null;
}

/** Hand-maintained app types. New API shapes are generated in `api-types.ts`. */

export interface CompositionPart {
  cell_type: string;
  fraction: number;
  ci?: number[];
}

export interface SampleQuality {
  tumour_fraction: number;
  composition: CompositionPart[];
  verdict: "sufficient" | "marginal" | "insufficient";
  verdict_reason?: string | null;
}

export interface PatientPosition {
  umap_coords: [number, number] | number[];
  posterior_ellipse: { rx: number; ry: number; theta: number };
  cluster: { label: number; posterior_mass: number };
  cohort_density_ref: string;
  modalities_used: string[];
  cohort_points: Array<{ x: number; y: number }>;
  posterior_width?: number | null;
  tau?: number | null;
}

export interface MolecularState {
  pathways: Array<{ name: string; activity: number; z?: number | null }>;
  transcription_factors: Array<{
    name: string;
    activity: number;
    reliability: string;
    reliability_reason?: string | null;
  }>;
  discrepancies: Array<{ field: string; clinical: string; inferred: string; severity: string }>;
}

export interface PrognosticEstimate {
  point_days?: number | null;
  interval_days?: number[] | null;
  requested_coverage: number;
  empirical_coverage?: number | null;
  n: number;
  method: string;
  label: string;
  domain_note: string;
  validated: boolean;
}

export interface PathwayCandidates {
  basis: "pathway_activity_threshold";
  validated: boolean;
  threshold_rule: string;
  set_members: Array<{ drug: string; evidence_tier: string }>;
  excluded_count: number;
  n_scored?: number | null;
}

export interface AbstentionState {
  abstained: boolean;
  reason_code?: string | null;
  reason_text?: string | null;
  what_would_help: string[];
  sections_rendered: string[];
}

export interface PrototypePayload {
  schema_version: "v2_prototype";
  patient_id: string;
  role: string;
  title?: string | null;
  description?: string | null;
  state: number;
  banner?: string | null;
  modalities_present: string[];
  patient_metadata: PatientMetadata;
  sample_quality: SampleQuality;
  position: PatientPosition;
  molecular_state: MolecularState;
  prognostic_estimate?: PrognosticEstimate | null;
  pathway_candidates?: PathwayCandidates | null;
  modality_value_estimate: Array<{
    modality: string;
    present: boolean;
    posterior_width_reduction?: number | null;
  }>;
  abstention: AbstentionState;
  s4_ships: boolean;
  limitations: string[];
}

export interface DemoPatientSummary {
  patient_id: string;
  role: string;
  title: string;
  description: string;
  modalities: string[];
  expected_state?: number | null;
}

export interface AnalysisResult {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  patient_label: string;
  patient_metadata: PatientMetadata;
  administered_regimen: string[];
  revision?: number;
  signature_params?: { top_up: number; top_down: number } | null;
  cluster_prediction: ClusterPrediction | null;
  rna_projection?: RnaProjection | null;
  cluster_signature?: SignaturePanel | null;
  residual_signature?: SignaturePanel | null;
  overlap_nominations?: OverlapNomination[];
  overlap_exploratory?: OverlapNomination[];
  overlap_technical_excluded?: OverlapNomination[];
  display_gate_summary?: Record<string, unknown> | null;
  compound_registry_version?: string | null;
  analysis_summary?: {
    top_cluster?: number;
    top_probability?: number;
    confidence_level?: string;
    headline_nominations?: Array<{
      drug?: string | null;
      human_development_label?: string | null;
      weaker_percentile?: number | null;
      display_gate_reason?: string | null;
    }>;
    dominant_uncertainty?: string | null;
  } | null;
  clinical_comparators?: ClinicalComparator[];
  predictor_single_drugs?: PredictorDrugEvidence[];
  predictor_combinations?: PredictorCombination[];
  predictor_summary?: Record<string, unknown> | null;
  near_consensus?: Array<Record<string, unknown>>;
  overlap_summary?: Record<string, unknown> | null;
  almanac_combinations?: AlmanacCombination[];
  list1_drugs?: Array<Record<string, unknown>>;
  list2_drugs?: Array<Record<string, unknown>>;
  administered_regimen_pcr: SupportedPcrResult | null;
  top_candidate_drugs: DrugCandidate[];
  limitations?: string[];
  warnings: WarningOut[];
  error_message?: string | null;
  current_stage?: string | null;
  prototype?: PrototypePayload | null;
  v3_cohort?: import("./v3-types").V3CohortPayload | null;
  v3_patient?: import("./v3-types").V3PatientPayload | null;
  schema_version?: string | null;
  s4_ships?: boolean;
}

export interface AnalysisSubmitAck {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  poll_url?: string | null;
}

export interface AuditEvent {
  tool_name: string;
  input_summary: Record<string, unknown> | null;
  output_summary: Record<string, unknown> | null;
  duration_ms: number | null;
  created_at: string;
}

export interface CitationOut {
  title: string;
  year: number | null;
  doi: string | null;
  pmid: string | null;
  pmcid: string | null;
  journal: string | null;
  publisher: string | null;
  /** Repository the record came from (PMC, bioRxiv, arXiv...), not the journal. */
  source?: string | null;
  article_type: string | null;
  peer_reviewed: boolean | null;
  full_text_available: boolean | null;
  excerpt: string | null;
  stance: "supporting" | "conflicting" | "neutral" | "unclear";
  matched_queries: string[];
  credibility_score?: number | null;
  relevance_score?: number | null;
  combined_score?: number | null;
  evidence_rank?: number | null;
  ranking_explanation?: string | null;
}

export interface LiteratureQueryFamily {
  label: string;
  query_text: string;
  result_count: number;
  executed_at: string;
}

export interface LiteratureResult {
  drug: string;
  query_families: LiteratureQueryFamily[];
  citations: CitationOut[];
  deduplicated_count: number;
  raw_result_count: number;
  cache_hit: boolean;
  searched_at: string;
  unavailable_reason?: string;
}

export interface GeneLiteratureResult {
  gene: string;
  cluster_id: number;
  query_families: LiteratureQueryFamily[];
  citations: CitationOut[];
  deduplicated_count: number;
  raw_result_count: number;
  cache_hit: boolean;
  searched_at: string;
  interpretation_note: string;
  unavailable_reason?: string;
}

export interface TrialSite {
  facility: string | null;
  city: string | null;
  country: string | null;
  tier: number;
  distance_from_ireland_km: number | null;
}

export type CriterionStatus = "met" | "not_met" | "unknown";

export interface EligibilityCriterion {
  criterion_id?: string;
  /** Human-readable criterion label (preferred). */
  criterion?: string | null;
  /** Alias used by some UI consumers; prefer `criterion`. */
  text?: string | null;
  status: CriterionStatus;
  evidence?: string | null;
  rationale?: string | null;
  category?: string | null;
  source_excerpt?: string | null;
}

export interface TrialMatch {
  nct_id: string;
  title: string;
  status: string;
  phase: string | null;
  conditions: string[];
  interventions: string[];
  sites: TrialSite[];
  eligibility_assessment: "potentially_eligible" | "potentially_ineligible" | "insufficient_information";
  eligibility_notes: string[];
  eligibility_criteria?: EligibilityCriterion[];
  eligibility_criteria_text?: string;
  matched_drugs?: string[];
  url: string;
}

export interface TrialsResult {
  drug: string;
  trials: TrialMatch[];
  cache_hit: boolean;
  searched_at: string;
  unavailable_reason?: string;
}

export interface RunTrialsResult {
  run_id: string;
  patient_label: string;
  n_drugs_queried: number;
  trials: TrialMatch[];
  unavailable?: Array<{ drug: string; reason: string }>;
  searched_at?: string;
}

export interface CopilotChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CopilotChatSource {
  label: string;
  section: "patient" | "mofa" | "q5" | "drug" | "trial" | "literature";
}

export interface RationaleClaim {
  text: string;
  kind: "support" | "counter" | "uncertainty";
  evidence_keys: string[];
  citation_ids: string[];
  section: CopilotChatSource["section"];
}

export interface GroundedRationale {
  summary: string;
  supporting_claims: RationaleClaim[];
  counter_claims: RationaleClaim[];
  uncertainty: RationaleClaim[];
  citations: Record<string, unknown>[];
  used_llm: boolean;
  fallback_used: boolean;
  provider?: string | null;
  model?: string | null;
}

export interface WithheldAnswer {
  reasons: string[];
  unsupported_numbers: string[];
  unsupported_drugs: string[];
  banned_phrases: string[];
}

export interface CopilotChatResponse {
  answer: string;
  used_local_model: boolean;
  answer_source?: "model" | "deterministic";
  /** Present when the model's answer failed the grounding gate. */
  withheld?: WithheldAnswer | null;
  sources: CopilotChatSource[];
  rationale?: GroundedRationale | null;
  provider?: string | null;
  model?: string | null;
  safety_note: string;
}

export interface PublicHealth {
  status: string;
  public_demo_mode: boolean;
  allow_custom_uploads: boolean;
  llm_active_provider?: string | null;
  llm_active_model?: string | null;
}

export type ActiveView = "patient_analysis" | "clinical_trials";
