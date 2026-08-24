from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.cluster import ClusterPredictionOut
from app.schemas.drug import DrugCandidate, SupportedPcrResult
from app.schemas.patient import PatientMetadata
from app.schemas.prototype import PrototypePayload


class WarningOut(BaseModel):
    severity: Literal["info", "caution", "abstain"]
    message: str


class AuditEventOut(BaseModel):
    tool_name: str
    input_summary: dict | None
    output_summary: dict | None
    duration_ms: float | None
    created_at: dt.datetime


class AnalysisStageOut(BaseModel):
    stage_id: str
    label: str
    status: Literal["running", "completed", "failed"]
    detail: str | None = None
    created_at: dt.datetime | None = None


class AnalysisProgressOut(BaseModel):
    run_id: str
    status: Literal["pending", "running", "completed", "failed"]
    current_stage: str | None = None
    stages: list[AnalysisStageOut] = []
    error_message: str | None = None


class SignatureGeneOut(BaseModel):
    gene: str
    effect: float
    direction: Literal["up", "down"]
    pval: float | None = None
    fdr: float | None = None
    literature_count: int | None = None


class SignaturePanelOut(BaseModel):
    kind: Literal["cluster", "residual"]
    cluster_id: int
    top_up: int
    top_down: int
    n_up: int
    n_down: int
    genes: list[SignatureGeneOut] = []
    coverage_fraction: float | None = None
    genes_used: int | None = None
    warnings: list[str] = []


class RnaProjectionOut(BaseModel):
    method: str
    label: str
    patient: dict[str, float]
    reference: list[dict[str, Any]] = []
    n_reference_total: int | None = None
    n_reference_shown: int | None = None
    genes_used: int | None = None
    gene_coverage: float | None = None


class AlmanacCombinationOut(BaseModel):
    drug_a: str
    drug_b: str
    combination: str
    aligned_cell_lines: int
    aligned_cell_line_names: str | None = None
    aligned_median_almanac_combo_score: float | None = None
    aligned_pair_support: float | None = None
    component_support: float | None = None
    q2_percentile_a: float | None = None
    q2_percentile_b: float | None = None
    combination_priority: float | None = None
    cell_line_alignment_confidence: str | None = None
    interpretation: str | None = None
    rank: int | None = None


class OverlapNominationOut(BaseModel):
    drug: str
    canonical: str
    list1_percentile: float | None = None
    list2_percentile: float | None = None
    weaker_percentile: float | None = None
    stronger_percentile: float | None = None
    rank_product: float | None = None
    list1_rank: int | None = None
    list2_rank: int | None = None
    targets: list[str] = []
    evidence_tier: str | None = None
    indication_bucket: str | None = None
    robustness: dict[str, Any] | None = None
    q2_annotation: dict[str, Any] | None = None
    literature_summary: dict[str, Any] | None = None
    is_in_administered_regimen: bool = False
    nomination_rank: int | None = None
    support_class: Literal[
        "breast_cell_line_supported", "suggestive", "excluded_low_confidence"
    ] | None = None
    support_rank: int | None = None
    human_development_status: str | None = None
    human_development_label: str | None = None
    entity_type: str | None = None
    display_action: Literal["default_visible", "exploratory_only", "technical_excluded"] | None = None
    display_gate_reason: str | None = None
    registry_match_key: str | None = None


class AnalysisResultOut(BaseModel):
    run_id: str
    status: Literal["pending", "running", "completed", "failed"]
    created_at: dt.datetime
    patient_label: str
    patient_metadata: PatientMetadata
    administered_regimen: list[str]
    revision: int = 0
    signature_params: dict[str, int] | None = None
    cluster_prediction: ClusterPredictionOut | None = None
    rna_projection: RnaProjectionOut | None = None
    cluster_signature: SignaturePanelOut | None = None
    residual_signature: SignaturePanelOut | None = None
    overlap_nominations: list[OverlapNominationOut] = []
    overlap_exploratory: list[OverlapNominationOut] = []
    overlap_technical_excluded: list[OverlapNominationOut] = []
    display_gate_summary: dict[str, Any] | None = None
    compound_registry_version: str | None = None
    analysis_summary: dict[str, Any] | None = None
    clinical_comparators: list[dict[str, Any]] = []
    predictor_single_drugs: list[dict[str, Any]] = []
    predictor_combinations: list[dict[str, Any]] = []
    predictor_summary: dict[str, Any] | None = None
    near_consensus: list[dict[str, Any]] = []
    overlap_summary: dict[str, Any] | None = None
    almanac_combinations: list[AlmanacCombinationOut] = []
    list1_drugs: list[dict[str, Any]] = []
    list2_drugs: list[dict[str, Any]] = []
    administered_regimen_pcr: SupportedPcrResult | None = None
    top_candidate_drugs: list[DrugCandidate] = []
    limitations: list[str] = []
    warnings: list[WarningOut] = []
    error_message: str | None = None
    current_stage: str | None = None
    prototype: PrototypePayload | None = None
    v3_cohort: dict[str, Any] | None = None
    v3_patient: dict[str, Any] | None = None
    schema_version: str | None = None
    s4_ships: bool = False


class AnalysisSubmitAck(BaseModel):
    run_id: str
    status: Literal["pending", "running", "completed", "failed"]
    poll_url: str | None = None
