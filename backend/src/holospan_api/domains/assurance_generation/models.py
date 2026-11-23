from datetime import datetime
from enum import Enum as PythonEnum
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from holospan_api.core.database import Base


def _enum_values(enum_type: type[PythonEnum]) -> list[str]:
    return [str(item.value) for item in enum_type]


class AssuranceRunStatus(StrEnum):
    QUEUED = "queued"
    DISCOVERING = "discovering"
    CONTEXT_REVIEW = "context_review"
    PLANNING = "planning"
    GENERATING = "generating"
    SCENARIO_REVIEW = "scenario_review"
    PUBLISHED = "published"
    PAUSED = "paused"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContextSnapshotStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class ContextClaimStatus(StrEnum):
    SUPPORTED = "supported"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class AssuranceGenerationRunRecord(Base):
    __tablename__ = "assurance_generation_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_tenants.id", ondelete="RESTRICT"), nullable=False
    )
    system_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[AssuranceRunStatus] = mapped_column(
        Enum(
            AssuranceRunStatus,
            name="assurance_generation_run_status",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    source_manifest: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    budget_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    context_snapshot_id: Mapped[UUID | None] = mapped_column(nullable=True)
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
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_run_tenant_system",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_assurance_run_tenant_idempotency"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_assurance_run_tenant_id"),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 16 AND 128",
            name="ck_assurance_run_idempotency_length",
        ),
        Index(
            "ix_assurance_run_tenant_system_created",
            tenant_id,
            system_id,
            created_at.desc(),
            id.desc(),
        ),
    )


class AssuranceContextSnapshotRecord(Base):
    __tablename__ = "assurance_context_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_tenants.id", ondelete="RESTRICT"), nullable=False
    )
    system_id: Mapped[UUID] = mapped_column(nullable=False)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[ContextSnapshotStatus] = mapped_column(
        Enum(
            ContextSnapshotStatus,
            name="assurance_context_snapshot_status",
            values_callable=_enum_values,
        ),
        default=ContextSnapshotStatus.DRAFT,
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    critic_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    critic: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    review_comment: Mapped[str | None] = mapped_column(String(2000))
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("identity_principals.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_snapshot_tenant_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["assurance_generation_runs.tenant_id", "assurance_generation_runs.id"],
            name="fk_assurance_snapshot_tenant_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "system_id", "version", name="uq_assurance_snapshot_version"),
        UniqueConstraint("tenant_id", "id", name="uq_assurance_snapshot_tenant_id"),
        CheckConstraint("version > 0", name="ck_assurance_snapshot_version"),
        CheckConstraint("row_version > 0", name="ck_assurance_snapshot_row_version"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_assurance_snapshot_sha256"),
        CheckConstraint("critic_score BETWEEN 0 AND 1", name="ck_assurance_snapshot_critic_score"),
        Index(
            "ix_assurance_snapshot_tenant_system_created",
            tenant_id,
            system_id,
            created_at.desc(),
            id.desc(),
        ),
    )


class AssuranceContextClaimRecord(Base):
    __tablename__ = "assurance_context_claims"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    system_id: Mapped[UUID] = mapped_column(nullable=False)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    subject_key: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[ContextClaimStatus] = mapped_column(
        Enum(
            ContextClaimStatus,
            name="assurance_context_claim_status",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_claim_tenant_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["assurance_generation_runs.tenant_id", "assurance_generation_runs.id"],
            name="fk_assurance_claim_tenant_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["assurance_context_snapshots.tenant_id", "assurance_context_snapshots.id"],
            name="fk_assurance_claim_tenant_snapshot",
            ondelete="RESTRICT",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_assurance_claim_confidence"),
        Index("ix_assurance_claim_tenant_snapshot", tenant_id, snapshot_id, id),
    )


class AssuranceArtifactCitationRecord(Base):
    __tablename__ = "assurance_artifact_citations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    system_id: Mapped[UUID] = mapped_column(nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(nullable=False)
    source_id: Mapped[UUID] = mapped_column(nullable=False)
    locator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    locator: Mapped[str] = mapped_column(String(512), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_citation_tenant_system",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["system_context_sources.tenant_id", "system_context_sources.id"],
            name="fk_assurance_citation_tenant_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_assurance_citation_content_sha256",
        ),
        Index(
            "ix_assurance_citation_tenant_artifact",
            tenant_id,
            artifact_type,
            artifact_id,
        ),
    )
