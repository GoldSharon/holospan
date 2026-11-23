"""assurance discovery runs and reviewed context snapshots

Revision ID: 20261123_0004
Revises: 20261123_0003
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261123_0004"
down_revision: str | None = "20261123_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_status = postgresql.ENUM(
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
        name="assurance_generation_run_status",
        create_type=False,
    )
    snapshot_status = postgresql.ENUM(
        "draft",
        "approved",
        "rejected",
        "revoked",
        name="assurance_context_snapshot_status",
        create_type=False,
    )
    claim_status = postgresql.ENUM(
        "supported",
        "conflicting",
        "unknown",
        "rejected",
        name="assurance_context_claim_status",
        create_type=False,
    )
    run_status.create(op.get_bind(), checkfirst=True)
    snapshot_status.create(op.get_bind(), checkfirst=True)
    claim_status.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint(
        "uq_system_context_source_tenant_id",
        "system_context_sources",
        ["tenant_id", "id"],
    )
    op.create_table(
        "assurance_generation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("identity_tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("current_stage", sa.String(64), nullable=False),
        sa.Column("source_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("budget_profile", sa.String(32), nullable=False),
        sa.Column("budget_state", postgresql.JSONB(), nullable=False),
        sa.Column("workflow_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("context_snapshot_id", sa.Uuid()),
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
            name="fk_assurance_run_tenant_system",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_assurance_run_tenant_idempotency"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_assurance_run_tenant_id"),
        sa.CheckConstraint(
            "char_length(idempotency_key) BETWEEN 16 AND 128",
            name="ck_assurance_run_idempotency_length",
        ),
    )
    op.create_index(
        "ix_assurance_run_tenant_system_created",
        "assurance_generation_runs",
        ["tenant_id", "system_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "assurance_context_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("identity_tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", snapshot_status, nullable=False, server_default="draft"),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_bucket", sa.String(63), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False, unique=True),
        sa.Column("critic_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("critic", postgresql.JSONB(), nullable=False),
        sa.Column("review_comment", sa.String(2000)),
        sa.Column(
            "approved_by",
            sa.Uuid(),
            sa.ForeignKey("identity_principals.id", ondelete="RESTRICT"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_snapshot_tenant_system",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["assurance_generation_runs.tenant_id", "assurance_generation_runs.id"],
            name="fk_assurance_snapshot_tenant_run",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id", "system_id", "version", name="uq_assurance_snapshot_version"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_assurance_snapshot_tenant_id"),
        sa.CheckConstraint("version > 0", name="ck_assurance_snapshot_version"),
        sa.CheckConstraint("row_version > 0", name="ck_assurance_snapshot_row_version"),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name="ck_assurance_snapshot_sha256"
        ),
        sa.CheckConstraint(
            "critic_score BETWEEN 0 AND 1", name="ck_assurance_snapshot_critic_score"
        ),
    )
    op.create_index(
        "ix_assurance_snapshot_tenant_system_created",
        "assurance_context_snapshots",
        ["tenant_id", "system_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "assurance_context_claims",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("subject_key", sa.String(255), nullable=False),
        sa.Column("claim_type", sa.String(128), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("status", claim_status, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("extraction_method", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_claim_tenant_system",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["assurance_generation_runs.tenant_id", "assurance_generation_runs.id"],
            name="fk_assurance_claim_tenant_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "snapshot_id"],
            ["assurance_context_snapshots.tenant_id", "assurance_context_snapshots.id"],
            name="fk_assurance_claim_tenant_snapshot",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_assurance_claim_confidence"
        ),
    )
    op.create_index(
        "ix_assurance_claim_tenant_snapshot",
        "assurance_context_claims",
        ["tenant_id", "snapshot_id", "id"],
    )

    op.create_table(
        "assurance_artifact_citations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("locator_type", sa.String(32), nullable=False),
        sa.Column("locator", sa.String(512), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "system_id"],
            ["system_context_systems.tenant_id", "system_context_systems.id"],
            name="fk_assurance_citation_tenant_system",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["system_context_sources.tenant_id", "system_context_sources.id"],
            name="fk_assurance_citation_tenant_source",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_assurance_citation_content_sha256",
        ),
    )
    op.create_index(
        "ix_assurance_citation_tenant_artifact",
        "assurance_artifact_citations",
        ["tenant_id", "artifact_type", "artifact_id"],
    )

    op.execute(
        """
        INSERT INTO identity_tenant_permissions (key, description) VALUES
          ('assurance_generation.context.read', 'Read discovered context snapshots'),
          ('assurance_generation.context.generate', 'Generate context from attributed evidence'),
          ('assurance_generation.context.review', 'Approve or reject context snapshots')
        """
    )
    op.execute(
        """
        INSERT INTO identity_tenant_role_permissions (role_id, permission_key) VALUES
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'assurance_generation.context.read'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'assurance_generation.context.generate'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'assurance_generation.context.review'),
          ('829da0ef-0e34-4e84-9388-108954919ac6', 'assurance_generation.context.read')
        """
    )

    for table in (
        "assurance_generation_runs",
        "assurance_context_snapshots",
        "assurance_context_claims",
        "assurance_artifact_citations",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_scope ON {table}
            TO holospan_tenant_runtime
            USING (tenant_id = identity_current_tenant_id())
            WITH CHECK (tenant_id = identity_current_tenant_id())
            """
        )
    op.execute(
        "GRANT SELECT, INSERT ON assurance_generation_runs TO holospan_tenant_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON assurance_context_snapshots TO holospan_tenant_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON assurance_context_claims, assurance_artifact_citations "
        "TO holospan_tenant_runtime"
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
            'assurance_generation.context.read',
            'assurance_generation.context.generate',
            'assurance_generation.context.review'
          )
        """
    )
    op.execute(
        """
        DELETE FROM identity_tenant_permissions
        WHERE key IN (
          'assurance_generation.context.read',
          'assurance_generation.context.generate',
          'assurance_generation.context.review'
        )
        """
    )
    op.drop_table("assurance_artifact_citations")
    op.drop_table("assurance_context_claims")
    op.drop_table("assurance_context_snapshots")
    op.drop_table("assurance_generation_runs")
    op.drop_constraint(
        "uq_system_context_source_tenant_id",
        "system_context_sources",
        type_="unique",
    )
    for enum_name in (
        "assurance_context_claim_status",
        "assurance_context_snapshot_status",
        "assurance_generation_run_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
