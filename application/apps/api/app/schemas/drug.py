from __future__ import annotations

from pydantic import BaseModel


class Q2DrugEvidence(BaseModel):
    drug: str
    raw_score: float | None
    z_score: float | None
    genes_used: int
    evidence_category: str | None = None
    model_support: float | None = None
    model_spearman: float | None = None
    external_spearman: float | None = None


class GctxClusterEvidence(BaseModel):
    cluster_id: int
    cluster_probability: float
    drug_rank: int
    reversal_score: float
    percentile: float
    n_signatures: int | None
    targets: list[str]
    n_drugs_in_cluster: int


class GctxDrugEvidence(BaseModel):
    drug: str
    blended_percentile: float | None
    clusters_with_data: int
    per_cluster: list[GctxClusterEvidence]


class ApplicabilityGate(BaseModel):
    represented: bool
    gate_passed: bool
    reason: str | None = None
    regimen_label: str | None = None
    validated_cohort: str | None = None
    validated_split: str | None = None
    held_out_auroc: float | None = None
    gate_threshold: float | None = None


class SupportedPcrResult(BaseModel):
    applicability_gate: ApplicabilityGate
    mofa_regimen_reversal_percentile: float | None
    mofa_regimen_reversal_note: str
    pcr_probability: float | None
    q2_regimen_score: dict | None


class TargetLiteratureCount(BaseModel):
    """Legacy compact counts plus V2 retrieved-reference summary fields."""

    model_config = {"extra": "allow"}

    drug: str | None = None
    total_citations: int | None = None
    supporting: int | None = None
    conflicting: int | None = None
    neutral: int | None = None
    unclear: int | None = None
    retrieved_relevant_references: int | None = None
    stance_counts: dict[str, int] | None = None
    dominant_stance: str | None = None
    note: str | None = None
    unavailable_reason: str | None = None
    cache_hit: bool | None = None


class DrugCandidate(BaseModel):
    """One nominated drug with every evidence component kept separate --
    there is deliberately no single overall score or tier."""

    model_config = {"extra": "allow"}

    drug: str
    targets: list[str]
    gctx_evidence: GctxDrugEvidence | None = None
    q2_evidence: Q2DrugEvidence | None = None
    literature_summary: TargetLiteratureCount | dict | None = None
    is_in_administered_regimen: bool = False
    evidence_tier: str | None = None
    list1_percentile: float | None = None
    list2_percentile: float | None = None
    indication_bucket: str | None = None
    robustness: dict | None = None
