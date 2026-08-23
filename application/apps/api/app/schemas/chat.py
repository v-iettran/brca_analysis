from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.rationale import GroundedRationaleResponse


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class CopilotChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=8)
    selected_drug: str | None = None
    selected_cluster: int | None = None
    active_view: Literal["patient_analysis", "clinical_trials"] | None = None


class ChatSource(BaseModel):
    label: str
    section: Literal["patient", "mofa", "q5", "drug", "trial", "literature"]


class CopilotChatResponse(BaseModel):
    answer: str
    used_local_model: bool
    sources: list[ChatSource]
    rationale: GroundedRationaleResponse | None = None
    provider: str | None = None
    model: str | None = None
    safety_note: str = (
        "Research evidence summary only. This response does not provide a diagnosis "
        "or guide clinical care."
    )
