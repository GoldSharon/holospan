"""system source metadata and storage attribution

Revision ID: 20261123_0003
Revises: 20261122_0002
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261123_0003"
down_revision: str | None = "20261122_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    source_kind = postgresql.ENUM(
        "context_document",
        "api_contract",
        name="system_context_source_kind",
        create_type=False,
    )
    source_status = postgresql.ENUM(
        "stored",
        name="system_context_source_status",
        create_type=False,
    )
    source_kind.create(op.get_bind(), checkfirst=True)
    source_status.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint(
        "uq_system_context_system_tenant_id",
        "system_context_systems",
        ["tenant_id", "id"],
    )
    op.create_table(
        "system_context_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("identity_tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("kind", source_kind, nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("declared_media_type", sa.String(127), nullable=False),
        sa.Column("detected_media_type", sa.String(127), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_bucket", sa.String(63), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("status", source_status, nullable=False, server_default="stored"),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("identity_principals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_system_context_source_tenant_system",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "byte_size BETWEEN 1 AND 2097152",
            name="ck_system_context_source_byte_size",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_system_context_source_sha256",
        ),
    )
    op.create_index(
        "ix_system_context_source_tenant_system_created",
        "system_context_sources",
        ["tenant_id", "system_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.execute(
        """
        INSERT INTO identity_tenant_permissions (key, description) VALUES
          ('system_context.sources.read', 'Read tenant system source metadata'),
          ('system_context.sources.manage', 'Upload and manage tenant system sources')
        """
    )
    op.execute(
        """
        INSERT INTO identity_tenant_role_permissions (role_id, permission_key) VALUES
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'system_context.sources.read'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'system_context.sources.manage'),
          ('829da0ef-0e34-4e84-9388-108954919ac6', 'system_context.sources.read')
        """
    )
    op.execute("ALTER TABLE system_context_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE system_context_sources FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY system_context_source_tenant_scope ON system_context_sources
        TO holospan_tenant_runtime
        USING (tenant_id = identity_current_tenant_id())
        WITH CHECK (tenant_id = identity_current_tenant_id())
        """
    )
    op.execute(
        "GRANT SELECT, INSERT ON system_context_sources TO holospan_tenant_runtime"
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM identity_tenant_role_permissions
        WHERE role_id IN (
          '044ac191-98c7-45ef-8d40-e5cda2dedf6e'::uuid,
          '829da0ef-0e34-4e84-9388-108954919ac6'::uuid
        )
          AND permission_key IN (
            'system_context.sources.read', 'system_context.sources.manage'
          )
        """
    )
    op.execute(
        """
        DELETE FROM identity_tenant_permissions
        WHERE key IN ('system_context.sources.read', 'system_context.sources.manage')
        """
    )
    op.drop_table("system_context_sources")
    op.drop_constraint(
        "uq_system_context_system_tenant_id",
        "system_context_systems",
        type_="unique",
    )
    op.execute("DROP TYPE IF EXISTS system_context_source_status")
    op.execute("DROP TYPE IF EXISTS system_context_source_kind")
