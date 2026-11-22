from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from holospan_api.domains.system_context.models import (
    LifecycleStage,
    SystemStatus,
    SystemType,
)


class CreateSystemRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(min_length=2, max_length=120, alias="displayName")
    slug: str = Field(
        min_length=3,
        max_length=63,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$",
    )
    description: str | None = Field(default=None, max_length=2000)
    system_type: SystemType = Field(alias="systemType")
    lifecycle_stage: LifecycleStage = Field(alias="lifecycleStage")

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("displayName must contain at least two visible characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SystemSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    tenant_id: UUID = Field(alias="tenantId")
    display_name: str = Field(alias="displayName")
    slug: str
    description: str | None = None
    system_type: SystemType = Field(alias="systemType")
    lifecycle_stage: LifecycleStage = Field(alias="lifecycleStage")
    status: SystemStatus
    created_by: UUID = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class SystemList(BaseModel):
    items: list[SystemSummary]
