from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from holospan_api.core.database import Base


class RecordStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class SessionPlane(StrEnum):
    TENANT = "tenant"
    PLATFORM = "platform"


class AuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Principal(Timestamped, Base):
    __tablename__ = "identity_principals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="identity_record_status"),
        default=RecordStatus.ACTIVE,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_principal_issuer_subject"),)


class Tenant(Timestamped, Base):
    __tablename__ = "identity_tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="tenant_record_status"),
        default=RecordStatus.ACTIVE,
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("identity_principals.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (Index("ix_tenant_created_id", "created_at", "id"),)


class Membership(Timestamped, Base):
    __tablename__ = "identity_memberships"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("identity_tenants.id"), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(ForeignKey("identity_principals.id"), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus, name="membership_record_status"),
        default=RecordStatus.ACTIVE,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "principal_id", name="uq_membership_tenant_principal"),
        UniqueConstraint("id", "tenant_id", name="uq_membership_id_tenant"),
        Index("ix_membership_tenant_status", "tenant_id", "status"),
        Index("ix_membership_principal_status", "principal_id", "status"),
        Index("ix_membership_tenant_created_id", "tenant_id", "created_at", "id"),
        Index(
            "ix_membership_principal_status_tenant",
            "principal_id",
            "status",
            "tenant_id",
        ),
    )


class TenantRole(Timestamped, Base):
    __tablename__ = "identity_tenant_roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_tenants.id"))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_tenant_role_id_tenant"),
        Index(
            "uq_tenant_role_global_key",
            "key",
            unique=True,
            postgresql_where=(tenant_id.is_(None)),
        ),
        Index(
            "uq_tenant_role_local_key",
            "tenant_id",
            "key",
            unique=True,
            postgresql_where=(tenant_id.is_not(None)),
        ),
    )


class TenantPermission(Base):
    __tablename__ = "identity_tenant_permissions"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class TenantRolePermission(Base):
    __tablename__ = "identity_tenant_role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_tenant_roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_key: Mapped[str] = mapped_column(
        ForeignKey("identity_tenant_permissions.key", ondelete="CASCADE"), primary_key=True
    )


class MembershipRole(Base):
    __tablename__ = "identity_membership_roles"

    membership_id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_tenant_roles.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id", "tenant_id"],
            ["identity_memberships.id", "identity_memberships.tenant_id"],
            ondelete="CASCADE",
        ),
        Index("ix_membership_role_tenant", "tenant_id", "membership_id"),
    )


class PlatformRole(Timestamped, Base):
    __tablename__ = "identity_platform_roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlatformPermission(Base):
    __tablename__ = "identity_platform_permissions"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class PlatformRolePermission(Base):
    __tablename__ = "identity_platform_role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_platform_roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_key: Mapped[str] = mapped_column(
        ForeignKey("identity_platform_permissions.key", ondelete="CASCADE"), primary_key=True
    )


class PrincipalPlatformRole(Base):
    __tablename__ = "identity_principal_platform_roles"

    principal_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_principals.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_platform_roles.id", ondelete="CASCADE"), primary_key=True
    )


class BrowserSession(Base):
    __tablename__ = "identity_browser_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_digest: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True, nullable=False)
    csrf_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(ForeignKey("identity_principals.id"), nullable=False)
    plane: Mapped[SessionPlane] = mapped_column(
        Enum(SessionPlane, name="identity_session_plane"), nullable=False
    )
    auth_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_browser_session_active", "expires_at", "revoked_at"),)


class AuthorizationAuditOutbox(Base):
    __tablename__ = "identity_authorization_audit_outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    stream: Mapped[str] = mapped_column(String(40), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_tenants.id"))
    actor_principal_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_principals.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(255))
    outcome: Mapped[AuditOutcome] = mapped_column(
        Enum(AuditOutcome, name="identity_audit_outcome"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    session_type: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    before_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    after_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_audit_outbox_pending", "published_at", "occurred_at"),
        Index("ix_audit_outbox_tenant_time", "tenant_id", "occurred_at"),
    )


class SealedAuthorizationAuditEvent(Base):
    __tablename__ = "identity_sealed_authorization_audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    stream_id: Mapped[str] = mapped_column(String(80), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column()
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    previous_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    event_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    sealer_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    sealed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("stream_id", "sequence", name="uq_sealed_audit_stream_sequence"),
        Index("ix_sealed_audit_tenant_time", "tenant_id", "sealed_at"),
    )


class RlsSigningKey(Base):
    """Database-owned key material; runtime roles receive no table privileges."""

    __tablename__ = "identity_rls_signing_keys"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    secret: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_identity_rls_single_key"),)
