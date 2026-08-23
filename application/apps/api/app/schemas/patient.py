from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatientMetadata(BaseModel):
    """Oncology metadata. Extra demo-enriched fields are allowed and preserved."""

    model_config = ConfigDict(extra="allow")

    age_at_diagnosis: float | None = None
    er_status: str | None = None
    her2_status: str | None = None
    pr_status: str | None = None
    claudin_subtype: str | None = None
    histological_subtype: str | None = None
    lymph_nodes_positive: float | None = None
    menopausal_state: str | None = None
    nottingham_prognostic_index: float | None = None
    tumor_stage: str | None = None
    tumor_grade: int | None = None
    tumor_size_mm: float | None = None
    ecog_status: int | None = None
    prior_therapy: str | None = None
    organ_function: dict[str, Any] | None = None
    location: dict[str, Any] | None = None
    field_provenance: dict[str, Any] | None = None

    @field_validator("er_status", "pr_status", mode="before")
    @classmethod
    def _fix_metabric_ihc_typo(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() == "positve":
            return "Positive"
        return value


class PatientProfileIn(BaseModel):
    """A single patient's RNA + metadata submission.

    ``expression`` maps gene symbol -> value (e.g. log2 microarray intensity
    or log2(TPM+1) RNA-seq). Values are aligned to the reference gene
    universe server-side; unmapped/missing genes reduce gene coverage and can
    trigger abstention (see ``pipeline_core.config.MIN_GENE_COVERAGE``).
    """

    patient_label: str = Field(
        ..., description="De-identified label only (e.g. 'SYN-HIG-...' or a local MRN alias). Never a real name."
    )
    expression: dict[str, float] = Field(..., min_length=1)
    metadata: PatientMetadata = Field(default_factory=PatientMetadata)
    administered_regimen: list[str] = Field(
        default_factory=list, description="Lower-case drug names, e.g. ['5-fluorouracil','doxorubicin','paclitaxel']."
    )
    top_up: int | None = Field(default=None, description="Signature up-arm size (default 150).")
    top_down: int | None = Field(default=None, description="Signature down-arm size (default 150).")

    @field_validator("expression")
    @classmethod
    def _no_nan_values(cls, value: dict[str, float]) -> dict[str, float]:
        import math

        return {k: v for k, v in value.items() if v is not None and math.isfinite(v)}

    @field_validator("administered_regimen")
    @classmethod
    def _normalize_regimen(cls, value: list[str]) -> list[str]:
        return [d.strip().lower() for d in value if d and d.strip()]


class RecalculateRequest(BaseModel):
    top_up: int = 150
    top_down: int = 150
