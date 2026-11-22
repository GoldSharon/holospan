from datetime import datetime
from enum import Enum as PythonEnum
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from holospan_api.core.database import Base


class SystemType(StrEnum):
    AGENT = "agent"
    RAG = "rag"
    WORKFLOW = "workflow"
    MODEL = "model"
    API = "api"
    OTHER = "other"


class LifecycleStage(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class SystemStatus(StrEnum):
    DRAFT = "draft"


def _enum_values(enum_type: type[PythonEnum]) -> list[str]:
    return [str(item.value) for item in enum_type]


class SystemRecord(Base):
    __tablename__ = "system_context_systems"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_tenants.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    system_type: Mapped[SystemType] = mapped_column(
        Enum(
            SystemType,
            name="system_context_system_type",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    lifecycle_stage: Mapped[LifecycleStage] = mapped_column(
        Enum(
            LifecycleStage,
            name="system_context_lifecycle_stage",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    status: Mapped[SystemStatus] = mapped_column(
        Enum(
            SystemStatus,
            name="system_context_system_status",
            values_callable=_enum_values,
        ),
        default=SystemStatus.DRAFT,
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("identity_principals.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_system_context_tenant_slug"),
        CheckConstraint(
            "char_length(display_name) BETWEEN 2 AND 120",
            name="ck_system_context_display_name_length",
        ),
        CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$'",
            name="ck_system_context_slug_format",
        ),
        CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="ck_system_context_description_length",
        ),
        Index(
            "ix_system_context_tenant_created",
            tenant_id,
            created_at.desc(),
            id.desc(),
        ),
    )
