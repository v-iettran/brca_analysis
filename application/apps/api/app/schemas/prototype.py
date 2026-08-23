"""v2 prototype payload contracts (B2–B7)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CompositionPart(BaseModel):
    cell_type: str
    fraction: float
    ci: list[float] = Field(default_factory=list)


class SampleQuality(BaseModel):
    tumour_fraction: float
    composition: list[CompositionPart] = Field(default_factory=list)
    verdict: Literal["sufficient", "marginal", "insufficient"]
    verdict_reason: str | None = None


class PosteriorEllipse(BaseModel):
    rx: float
    ry: float
    theta: float


class ClusterBadge(BaseModel):
    label: int
    posterior_mass: float


class PatientPosition(BaseModel):
    umap_coords: list[float]
    posterior_ellipse: PosteriorEllipse
    cluster: ClusterBadge
    cohort_density_ref: str = "tcga_brca_v2"
    modalities_used: list[str] = Field(default_factory=list)
    cohort_points: list[dict[str, Any]] = Field(default_factory=list)
    posterior_width: float | None = None
    tau: float | None = None


class PathwayActivity(BaseModel):
    name: str
    activity: float
    z: float | None = None


class TranscriptionFactor(BaseModel):
    name: str
    activity: float
    reliability: str = "high"
    reliability_reason: str | None = None


class ClinicalDiscrepancy(BaseModel):
    field: str
    clinical: str
    inferred: str
    severity: str = "note"


class MolecularState(BaseModel):
    pathways: list[PathwayActivity] = Field(default_factory=list)
    transcription_factors: list[TranscriptionFactor] = Field(default_factory=list)
    discrepancies: list[ClinicalDiscrepancy] = Field(default_factory=list)


class SetMember(BaseModel):
    drug: str
    evidence_tier: str = "B"


class PredictionSet(BaseModel):
    coverage_level: float = 0.90
    set_members: list[SetMember] = Field(default_factory=list)
    set_width_note: str | None = None
    excluded_count: int = 0
    n_scored: int | None = None


class ModalityValue(BaseModel):
    modality: str
    present: bool
    posterior_width_reduction: float | None = None


class AbstentionState(BaseModel):
    abstained: bool
    reason_code: str | None = None
    reason_text: str | None = None
    what_would_help: list[str] = Field(default_factory=list)
    sections_rendered: list[str] = Field(default_factory=list)


class PrototypePayload(BaseModel):
    schema_version: Literal["v2_prototype"] = "v2_prototype"
    patient_id: str
    role: str
    title: str | None = None
    description: str | None = None
    state: int = 1
    banner: str | None = None
    modalities_present: list[str] = Field(default_factory=list)
    patient_metadata: dict[str, Any] = Field(default_factory=dict)
    sample_quality: SampleQuality
    position: PatientPosition
    molecular_state: MolecularState
    prediction_set: PredictionSet | None = None
    modality_value_estimate: list[ModalityValue] = Field(default_factory=list)
    abstention: AbstentionState
    s4_ships: bool = False
    limitations: list[str] = Field(default_factory=list)


class DemoPatientSummary(BaseModel):
    patient_id: str
    role: str
    title: str
    description: str
    modalities: list[str] = Field(default_factory=list)
    expected_state: int | None = None
