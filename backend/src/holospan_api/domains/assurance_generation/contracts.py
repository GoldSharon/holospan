from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

BudgetProfile = Literal["economy", "balanced", "high_assurance"]
ReviewDecision = Literal["approve", "reject"]
RunStatus = Literal[
    "queued",
    "discovering",
    "context_review",
    "planning",
    "generating",
    "scenario_review",
    "published",
    "paused",
    "failed",
    "cancelled",
]
SnapshotStatus = Literal["draft", "approved", "rejected", "revoked"]


class StartDiscoveryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    source_ids: list[UUID] = Field(alias="sourceIds", min_length=1, max_length=20)
    objective: str | None = Field(default=None, max_length=1000)
    budget_profile: BudgetProfile = Field(default="balanced", alias="budgetProfile")

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("sourceIds must be unique")
        return value


class ReviewContextRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    decision: ReviewDecision
    comment: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(alias="expectedVersion", ge=1)

    @field_validator("comment")
    @classmethod
    def clean_comment(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("comment must contain visible characters")
        return cleaned


class ContextSnapshotSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    system_id: UUID = Field(alias="systemId")
    version: int
    row_version: int = Field(alias="rowVersion")
    status: SnapshotStatus
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    critic_score: float = Field(alias="criticScore", ge=0, le=1)
    content: dict[str, Any]
    approved_by: UUID | None = Field(default=None, alias="approvedBy")
    approved_at: datetime | None = Field(default=None, alias="approvedAt")
    created_at: datetime = Field(alias="createdAt")


class ContextSnapshotList(BaseModel):
    items: list[ContextSnapshotSummary]


class DiscoveryRunDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    system_id: UUID = Field(alias="systemId")
    status: RunStatus
    current_stage: str = Field(alias="currentStage")
    source_ids: list[UUID] = Field(alias="sourceIds")
    context_snapshot: ContextSnapshotSummary | None = Field(default=None, alias="contextSnapshot")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
