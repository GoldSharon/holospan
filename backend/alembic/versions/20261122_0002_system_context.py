"""tenant system context foundation

Revision ID: 20261122_0002
Revises: 20261122_0001
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261122_0002"
down_revision: str | None = "20261122_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    system_type = postgresql.ENUM(
        "agent",
        "rag",
        "workflow",
        "model",
        "api",
        "other",
        name="system_context_system_type",
        create_type=False,
    )
    lifecycle_stage = postgresql.ENUM(
        "development",
        "staging",
        "production",
        name="system_context_lifecycle_stage",
        create_type=False,
    )
    system_status = postgresql.ENUM(
        "draft", name="system_context_system_status", create_type=False
    )
    system_type.create(op.get_bind(), checkfirst=True)
    lifecycle_stage.create(op.get_bind(), checkfirst=True)
    system_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "system_context_systems",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("identity_tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("system_type", system_type, nullable=False),
        sa.Column("lifecycle_stage", lifecycle_stage, nullable=False),
        sa.Column("status", system_status, nullable=False, server_default="draft"),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("identity_principals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_system_context_tenant_slug"),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 2 AND 120",
            name="ck_system_context_display_name_length",
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$'",
            name="ck_system_context_slug_format",
        ),
        sa.CheckConstraint(
            "description IS NULL OR char_length(description) <= 2000",
            name="ck_system_context_description_length",
        ),
    )
    op.create_index(
        "ix_system_context_tenant_created",
        "system_context_systems",
        ["tenant_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.execute(
        """
        INSERT INTO identity_tenant_permissions (key, description) VALUES
          ('system_context.systems.read', 'Read tenant system metadata'),
          ('system_context.systems.manage', 'Create and manage tenant system metadata')
        """
    )
    op.execute(
        """
        INSERT INTO identity_tenant_role_permissions (role_id, permission_key) VALUES
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'system_context.systems.read'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'system_context.systems.manage'),
          ('829da0ef-0e34-4e84-9388-108954919ac6', 'system_context.systems.read')
        """
    )
    op.execute("ALTER TABLE system_context_systems ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE system_context_systems FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY system_context_tenant_scope ON system_context_systems
        TO holospan_tenant_runtime
        USING (tenant_id = identity_current_tenant_id())
        WITH CHECK (tenant_id = identity_current_tenant_id())
        """
    )
    op.execute(
        "GRANT SELECT, INSERT ON system_context_systems TO holospan_tenant_runtime"
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
            'system_context.systems.read', 'system_context.systems.manage'
          )
        """
    )
    op.execute(
        """
        DELETE FROM identity_tenant_permissions
        WHERE key IN ('system_context.systems.read', 'system_context.systems.manage')
        """
    )
    op.drop_table("system_context_systems")
    for enum_name in (
        "system_context_system_status",
        "system_context_lifecycle_stage",
        "system_context_system_type",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
