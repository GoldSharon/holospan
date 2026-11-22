# ruff: noqa: E501
"""identity access foundation

Revision ID: 20261122_0001
Revises:
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261122_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_ADMIN_ROLE = "044ac191-98c7-45ef-8d40-e5cda2dedf6e"
TENANT_VIEWER_ROLE = "829da0ef-0e34-4e84-9388-108954919ac6"
PLATFORM_ADMIN_ROLE = "91199041-b463-4a50-b2bb-28f7128c2ba5"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'holospan_auth_runtime') THEN
            CREATE ROLE holospan_auth_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'holospan_tenant_runtime') THEN
            CREATE ROLE holospan_tenant_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'holospan_audit_writer') THEN
            CREATE ROLE holospan_audit_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
        END $$;
        """
    )

    record_status = sa.Enum("ACTIVE", "SUSPENDED", name="identity_record_status")
    tenant_status = sa.Enum("ACTIVE", "SUSPENDED", name="tenant_record_status")
    membership_status = sa.Enum("ACTIVE", "SUSPENDED", name="membership_record_status")
    session_plane = sa.Enum("TENANT", "PLATFORM", name="identity_session_plane")
    audit_outcome = sa.Enum(
        "ALLOWED", "DENIED", "SUCCEEDED", "FAILED", name="identity_audit_outcome"
    )

    op.create_table(
        "identity_principals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("issuer", sa.String(512), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("display_name", sa.String(120)),
        sa.Column("status", record_status, nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("issuer", "subject", name="uq_principal_issuer_subject"),
    )
    op.create_table(
        "identity_tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("status", tenant_status, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("identity_principals.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_tenant_created_id", "identity_tenants", ["created_at", "id"]
    )
    op.create_table(
        "identity_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("identity_tenants.id"), nullable=False),
        sa.Column(
            "principal_id", sa.Uuid(), sa.ForeignKey("identity_principals.id"), nullable=False
        ),
        sa.Column("status", membership_status, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "principal_id", name="uq_membership_tenant_principal"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_membership_id_tenant"),
    )
    op.create_index("ix_membership_tenant_status", "identity_memberships", ["tenant_id", "status"])
    op.create_index(
        "ix_membership_principal_status", "identity_memberships", ["principal_id", "status"]
    )
    op.create_index(
        "ix_membership_tenant_created_id",
        "identity_memberships",
        ["tenant_id", "created_at", "id"],
    )
    op.create_index(
        "ix_membership_principal_status_tenant",
        "identity_memberships",
        ["principal_id", "status", "tenant_id"],
    )

    op.create_table(
        "identity_tenant_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("identity_tenants.id")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_tenant_role_id_tenant"),
    )
    op.create_index(
        "uq_tenant_role_global_key",
        "identity_tenant_roles",
        ["key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_tenant_role_local_key",
        "identity_tenant_roles",
        ["tenant_id", "key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_table(
        "identity_tenant_permissions",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
    )
    op.create_table(
        "identity_tenant_role_permissions",
        sa.Column(
            "role_id",
            sa.Uuid(),
            sa.ForeignKey("identity_tenant_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_key",
            sa.String(120),
            sa.ForeignKey("identity_tenant_permissions.key", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "identity_membership_roles",
        sa.Column("membership_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role_id",
            sa.Uuid(),
            sa.ForeignKey("identity_tenant_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.ForeignKeyConstraint(
            ["membership_id", "tenant_id"],
            ["identity_memberships.id", "identity_memberships.tenant_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_membership_role_tenant", "identity_membership_roles", ["tenant_id", "membership_id"]
    )

    op.create_table(
        "identity_platform_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(80), unique=True, nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "identity_platform_permissions",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("description", sa.String(255), nullable=False),
    )
    op.create_table(
        "identity_platform_role_permissions",
        sa.Column(
            "role_id",
            sa.Uuid(),
            sa.ForeignKey("identity_platform_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_key",
            sa.String(120),
            sa.ForeignKey("identity_platform_permissions.key", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "identity_principal_platform_roles",
        sa.Column(
            "principal_id",
            sa.Uuid(),
            sa.ForeignKey("identity_principals.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.Uuid(),
            sa.ForeignKey("identity_platform_roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "identity_browser_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token_digest", sa.LargeBinary(32), unique=True, nullable=False),
        sa.Column("csrf_digest", sa.LargeBinary(32), nullable=False),
        sa.Column(
            "principal_id", sa.Uuid(), sa.ForeignKey("identity_principals.id"), nullable=False
        ),
        sa.Column("plane", session_plane, nullable=False),
        sa.Column("auth_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_browser_session_active", "identity_browser_sessions", ["expires_at", "revoked_at"]
    )

    op.create_table(
        "identity_authorization_audit_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("stream", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("identity_tenants.id")),
        sa.Column("actor_principal_id", sa.Uuid(), sa.ForeignKey("identity_principals.id")),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target_type", sa.String(80)),
        sa.Column("target_id", sa.String(255)),
        sa.Column("outcome", audit_outcome, nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("principal_type", sa.String(40), nullable=False),
        sa.Column("session_type", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("before_digest", sa.LargeBinary(32)),
        sa.Column("after_digest", sa.LargeBinary(32)),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_audit_outbox_pending",
        "identity_authorization_audit_outbox",
        ["published_at", "occurred_at"],
    )
    op.create_index(
        "ix_audit_outbox_tenant_time",
        "identity_authorization_audit_outbox",
        ["tenant_id", "occurred_at"],
    )
    op.create_table(
        "identity_sealed_authorization_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("stream_id", sa.String(80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("previous_digest", sa.LargeBinary(32)),
        sa.Column("event_digest", sa.LargeBinary(32), nullable=False),
        sa.Column("sealer_identity", sa.String(255), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream_id", "sequence", name="uq_sealed_audit_stream_sequence"),
    )
    op.create_index(
        "ix_sealed_audit_tenant_time",
        "identity_sealed_authorization_audit_events",
        ["tenant_id", "sealed_at"],
    )
    op.create_table(
        "identity_rls_signing_keys",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("secret", sa.LargeBinary(32), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_identity_rls_single_key"),
    )
    op.execute(
        "INSERT INTO identity_rls_signing_keys (id, secret) VALUES (1, gen_random_bytes(32))"
    )

    _seed_authorization()
    _create_scope_guards()
    _create_rls_context()
    _create_rls_policies()
    _create_audit_sealer()
    _grant_runtime_privileges()


def _seed_authorization() -> None:
    op.execute(
        """
        INSERT INTO identity_tenant_permissions (key, description) VALUES
          ('tenant.read', 'Read tenant metadata'),
          ('tenant.members.read', 'Read tenant members'),
          ('tenant.members.manage', 'Manage tenant member roles'),
          ('tenant.audit.read', 'Read tenant authorization audit evidence')
        """
    )
    op.execute(
        """
        INSERT INTO identity_platform_permissions (key, description) VALUES
          ('platform.tenants.read', 'Read platform tenant metadata'),
          ('platform.tenants.manage', 'Create and suspend tenant metadata')
        """
    )
    op.execute(
        """
        INSERT INTO identity_tenant_roles (id, key, display_name, tenant_id, is_system) VALUES
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'tenant_admin', 'Tenant administrator', NULL, true),
          ('829da0ef-0e34-4e84-9388-108954919ac6', 'viewer', 'Read-only viewer', NULL, true)
        """
    )
    op.execute(
        """
        INSERT INTO identity_tenant_role_permissions (role_id, permission_key) VALUES
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'tenant.read'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'tenant.members.read'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'tenant.members.manage'),
          ('044ac191-98c7-45ef-8d40-e5cda2dedf6e', 'tenant.audit.read'),
          ('829da0ef-0e34-4e84-9388-108954919ac6', 'tenant.read')
        """
    )
    op.execute(
        """
        INSERT INTO identity_platform_roles (id, key, display_name, is_system) VALUES
          ('91199041-b463-4a50-b2bb-28f7128c2ba5', 'platform_admin', 'Platform administrator', true)
        """
    )
    op.execute(
        """
        INSERT INTO identity_platform_role_permissions (role_id, permission_key) VALUES
          ('91199041-b463-4a50-b2bb-28f7128c2ba5', 'platform.tenants.read'),
          ('91199041-b463-4a50-b2bb-28f7128c2ba5', 'platform.tenants.manage')
        """
    )


def _create_scope_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION identity_validate_membership_role_scope() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE role_tenant uuid;
        BEGIN
          SELECT tenant_id INTO role_tenant FROM public.identity_tenant_roles WHERE id = NEW.role_id;
          IF NOT FOUND OR (role_tenant IS NOT NULL AND role_tenant <> NEW.tenant_id) THEN
            RAISE EXCEPTION 'invalid tenant role scope' USING ERRCODE = '42501';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER identity_membership_role_scope
          BEFORE INSERT OR UPDATE ON identity_membership_roles
          FOR EACH ROW EXECUTE FUNCTION identity_validate_membership_role_scope()
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_preserve_tenant_admin() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE admin_count bigint;
        DECLARE removed_admin boolean;
        BEGIN
          SELECT EXISTS (
            SELECT 1 FROM public.identity_tenant_roles
            WHERE id = OLD.role_id AND key = 'tenant_admin'
          ) INTO removed_admin;
          IF removed_admin THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(OLD.tenant_id::text, 0));
            SELECT count(DISTINCT m.id) INTO admin_count
            FROM public.identity_memberships m
            JOIN public.identity_membership_roles mr ON mr.membership_id = m.id
            JOIN public.identity_tenant_roles r ON r.id = mr.role_id
            WHERE m.tenant_id = OLD.tenant_id AND m.status = 'ACTIVE' AND r.key = 'tenant_admin';
            IF admin_count < 1 THEN
              RAISE EXCEPTION 'LAST_TENANT_ADMIN_REQUIRED' USING ERRCODE = '23514';
            END IF;
          END IF;
          RETURN OLD;
        END $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER identity_last_tenant_admin
          AFTER DELETE OR UPDATE ON identity_membership_roles
          DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW
          EXECUTE FUNCTION identity_preserve_tenant_admin()
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_preserve_active_admin_membership() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE was_admin boolean; DECLARE remaining_admins bigint;
        BEGIN
          SELECT EXISTS (
            SELECT 1 FROM public.identity_membership_roles mr
            JOIN public.identity_tenant_roles r ON r.id = mr.role_id
            WHERE mr.membership_id = OLD.id AND r.key = 'tenant_admin'
          ) INTO was_admin;
          IF OLD.status = 'ACTIVE' AND was_admin
             AND (TG_OP = 'DELETE' OR NEW.status <> 'ACTIVE') THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(OLD.tenant_id::text, 0));
            SELECT count(DISTINCT m.id) INTO remaining_admins
            FROM public.identity_memberships m
            JOIN public.identity_membership_roles mr ON mr.membership_id = m.id
            JOIN public.identity_tenant_roles r ON r.id = mr.role_id
            WHERE m.tenant_id = OLD.tenant_id AND m.status = 'ACTIVE'
              AND m.id <> OLD.id AND r.key = 'tenant_admin';
            IF remaining_admins < 1 THEN
              RAISE EXCEPTION 'LAST_TENANT_ADMIN_REQUIRED' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER identity_last_active_admin_membership
          AFTER DELETE OR UPDATE OF status ON identity_memberships
          DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW
          EXECUTE FUNCTION identity_preserve_active_admin_membership()
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_protect_canonical_tenant_admin_role() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          IF OLD.id = '044ac191-98c7-45ef-8d40-e5cda2dedf6e'::uuid
             OR (OLD.key = 'tenant_admin' AND OLD.tenant_id IS NULL AND OLD.is_system) THEN
            IF TG_OP = 'DELETE' OR NEW.id <> OLD.id OR NEW.key <> OLD.key
               OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
               OR NEW.is_system IS DISTINCT FROM OLD.is_system THEN
              RAISE EXCEPTION 'CANONICAL_TENANT_ADMIN_ROLE_IMMUTABLE' USING ERRCODE = '23514';
            END IF;
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER identity_canonical_tenant_admin_role
          BEFORE DELETE OR UPDATE ON identity_tenant_roles
          FOR EACH ROW EXECUTE FUNCTION identity_protect_canonical_tenant_admin_role()
        """
    )


def _create_rls_context() -> None:
    op.execute(
        """
        CREATE FUNCTION identity_activate_tenant_context(p_session_digest bytea, p_tenant_id uuid)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE principal uuid; DECLARE expires_epoch bigint; DECLARE material text; DECLARE signature text;
        BEGIN
          SELECT s.principal_id, extract(epoch FROM s.expires_at)::bigint
            INTO principal, expires_epoch
          FROM public.identity_browser_sessions s
          JOIN public.identity_principals p ON p.id = s.principal_id AND p.status = 'ACTIVE'
          JOIN public.identity_memberships m ON m.principal_id = s.principal_id
            AND m.tenant_id = p_tenant_id AND m.status = 'ACTIVE'
          JOIN public.identity_tenants t ON t.id = m.tenant_id AND t.status = 'ACTIVE'
          WHERE s.token_digest = p_session_digest AND s.plane = 'TENANT'
            AND s.revoked_at IS NULL AND s.expires_at > clock_timestamp();
          IF principal IS NULL THEN RAISE EXCEPTION 'invalid tenant context' USING ERRCODE = '42501'; END IF;
          material := p_tenant_id::text || '|' || principal::text || '|' || expires_epoch::text;
          SELECT encode(hmac(convert_to(material, 'UTF8'), secret, 'sha256'), 'hex') INTO signature
            FROM public.identity_rls_signing_keys WHERE id = 1;
          PERFORM set_config('app.holospan_context', material || '|' || signature, true);
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_current_tenant_id() RETURNS uuid
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE parts text[]; DECLARE material text; DECLARE expected text;
        BEGIN
          parts := string_to_array(current_setting('app.holospan_context', true), '|');
          IF array_length(parts, 1) <> 4 OR parts[3]::bigint <= extract(epoch FROM clock_timestamp())::bigint THEN
            RETURN NULL;
          END IF;
          material := parts[1] || '|' || parts[2] || '|' || parts[3];
          SELECT encode(hmac(convert_to(material, 'UTF8'), secret, 'sha256'), 'hex') INTO expected
            FROM public.identity_rls_signing_keys WHERE id = 1;
          IF expected IS NULL OR expected <> parts[4] THEN RETURN NULL; END IF;
          RETURN parts[1]::uuid;
        EXCEPTION WHEN others THEN RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_activate_auth_context(p_session_digest bytea)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE principal uuid; DECLARE auth_plane text; DECLARE expires_epoch bigint;
        DECLARE material text; DECLARE signature text;
        BEGIN
          SELECT s.principal_id, s.plane::text, extract(epoch FROM s.expires_at)::bigint
            INTO principal, auth_plane, expires_epoch
          FROM public.identity_browser_sessions s
          JOIN public.identity_principals p ON p.id = s.principal_id AND p.status = 'ACTIVE'
          WHERE s.token_digest = p_session_digest AND s.revoked_at IS NULL
            AND s.expires_at > clock_timestamp();
          IF principal IS NULL THEN
            RAISE EXCEPTION 'invalid authentication context' USING ERRCODE = '42501';
          END IF;
          material := principal::text || '|' || auth_plane || '|' || expires_epoch::text;
          SELECT encode(hmac(convert_to(material, 'UTF8'), secret, 'sha256'), 'hex')
            INTO signature FROM public.identity_rls_signing_keys WHERE id = 1;
          PERFORM set_config('app.holospan_auth_context', material || '|' || signature, true);
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_current_auth_claims()
        RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE parts text[]; DECLARE material text; DECLARE expected text;
        BEGIN
          parts := string_to_array(current_setting('app.holospan_auth_context', true), '|');
          IF array_length(parts, 1) <> 4
             OR parts[3]::bigint <= extract(epoch FROM clock_timestamp())::bigint THEN
            RETURN NULL;
          END IF;
          material := parts[1] || '|' || parts[2] || '|' || parts[3];
          SELECT encode(hmac(convert_to(material, 'UTF8'), secret, 'sha256'), 'hex')
            INTO expected FROM public.identity_rls_signing_keys WHERE id = 1;
          IF expected IS NULL OR expected <> parts[4] THEN RETURN NULL; END IF;
          RETURN parts;
        EXCEPTION WHEN others THEN RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_current_auth_principal_id() RETURNS uuid
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT (public.identity_current_auth_claims())[1]::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_auth_is_platform_admin() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT coalesce(
            (public.identity_current_auth_claims())[2] = 'PLATFORM'
            AND EXISTS (
              SELECT 1 FROM public.identity_principal_platform_roles pr
              JOIN public.identity_platform_roles r ON r.id = pr.role_id
              WHERE pr.principal_id = public.identity_current_auth_principal_id()
                AND r.key = 'platform_admin' AND r.is_system
            ), false
          )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_auth_has_tenant(p_tenant_id uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT EXISTS (
            SELECT 1 FROM public.identity_memberships m
            WHERE m.tenant_id = p_tenant_id AND m.status = 'ACTIVE'
              AND m.principal_id = public.identity_current_auth_principal_id()
          )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION identity_auth_has_membership(p_membership_id uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT EXISTS (
            SELECT 1 FROM public.identity_memberships m
            WHERE m.id = p_membership_id AND m.status = 'ACTIVE'
              AND m.principal_id = public.identity_current_auth_principal_id()
          )
        $$
        """
    )


def _create_rls_policies() -> None:
    for table in (
        "identity_tenants",
        "identity_memberships",
        "identity_membership_roles",
        "identity_authorization_audit_outbox",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    policies = (
        "CREATE POLICY identity_tenant_scope ON identity_tenants "
        "FOR SELECT TO holospan_tenant_runtime "
        "USING (id = identity_current_tenant_id())",
        "CREATE POLICY identity_membership_scope ON identity_memberships "
        "TO holospan_tenant_runtime USING (tenant_id = identity_current_tenant_id()) "
        "WITH CHECK (tenant_id = identity_current_tenant_id())",
        "CREATE POLICY identity_membership_role_scope_policy ON identity_membership_roles "
        "TO holospan_tenant_runtime USING (tenant_id = identity_current_tenant_id()) "
        "WITH CHECK (tenant_id = identity_current_tenant_id())",
        "CREATE POLICY identity_audit_outbox_scope ON identity_authorization_audit_outbox "
        "TO holospan_tenant_runtime USING (tenant_id = identity_current_tenant_id()) "
        "WITH CHECK (tenant_id = identity_current_tenant_id())",
        "CREATE POLICY identity_tenant_auth_control ON identity_tenants "
        "FOR SELECT TO holospan_auth_runtime USING "
        "(identity_auth_is_platform_admin() OR identity_auth_has_tenant(id))",
        "CREATE POLICY identity_tenant_auth_provision ON identity_tenants "
        "FOR INSERT TO holospan_auth_runtime WITH CHECK (identity_auth_is_platform_admin())",
        "CREATE POLICY identity_membership_auth_control ON identity_memberships "
        "FOR SELECT TO holospan_auth_runtime USING "
        "(identity_auth_is_platform_admin() OR principal_id = identity_current_auth_principal_id())",
        "CREATE POLICY identity_membership_auth_provision ON identity_memberships "
        "FOR INSERT TO holospan_auth_runtime WITH CHECK (identity_auth_is_platform_admin())",
        "CREATE POLICY identity_membership_role_auth_control ON identity_membership_roles "
        "FOR SELECT TO holospan_auth_runtime USING "
        "(identity_auth_is_platform_admin() OR identity_auth_has_membership(membership_id))",
        "CREATE POLICY identity_membership_role_auth_provision ON identity_membership_roles "
        "FOR INSERT TO holospan_auth_runtime WITH CHECK (identity_auth_is_platform_admin())",
        "CREATE POLICY identity_audit_outbox_auth_append "
        "ON identity_authorization_audit_outbox FOR INSERT TO holospan_auth_runtime WITH CHECK (true)",
    )
    for policy in policies:
        op.execute(policy)


def _create_audit_sealer() -> None:
    op.execute(
        """
        CREATE FUNCTION identity_seal_authorization_event(p_event_id uuid)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE event_row record; DECLARE next_sequence integer;
        DECLARE prior_digest bytea; DECLARE canonical_payload jsonb; DECLARE sealed_digest bytea;
        BEGIN
          SELECT * INTO event_row FROM public.identity_authorization_audit_outbox
            WHERE id = p_event_id AND published_at IS NULL FOR UPDATE;
          IF NOT FOUND THEN RETURN NULL; END IF;
          PERFORM pg_advisory_xact_lock(hashtextextended(event_row.stream, 1));
          SELECT sequence, event_digest INTO next_sequence, prior_digest
            FROM public.identity_sealed_authorization_audit_events
            WHERE stream_id = event_row.stream ORDER BY sequence DESC LIMIT 1;
          next_sequence := coalesce(next_sequence, 0) + 1;
          canonical_payload := to_jsonb(event_row) - 'published_at';
          sealed_digest := digest(
            convert_to(
              coalesce(encode(prior_digest, 'hex'), '') || '|' || next_sequence::text ||
              '|' || canonical_payload::text,
              'UTF8'
            ),
            'sha256'
          );
          INSERT INTO public.identity_sealed_authorization_audit_events (
            id, stream_id, sequence, tenant_id, payload, previous_digest,
            event_digest, sealer_identity, sealed_at
          ) VALUES (
            event_row.id, event_row.stream, next_sequence, event_row.tenant_id,
            canonical_payload, prior_digest, sealed_digest, session_user, clock_timestamp()
          );
          UPDATE public.identity_authorization_audit_outbox
            SET published_at = clock_timestamp() WHERE id = event_row.id;
          RETURN event_row.id;
        END $$
        """
    )


def _grant_runtime_privileges() -> None:
    grants = (
        "REVOKE ALL ON identity_rls_signing_keys FROM PUBLIC, holospan_auth_runtime, "
        "holospan_tenant_runtime, holospan_audit_writer",
        "REVOKE ALL ON identity_sealed_authorization_audit_events FROM PUBLIC, "
        "holospan_auth_runtime, holospan_tenant_runtime",
        "REVOKE ALL ON FUNCTION identity_activate_tenant_context(bytea, uuid) FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_current_tenant_id() FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_activate_auth_context(bytea) FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_current_auth_claims() FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_current_auth_principal_id() FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_auth_is_platform_admin() FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_auth_has_tenant(uuid) FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_auth_has_membership(uuid) FROM PUBLIC",
        "REVOKE ALL ON FUNCTION identity_seal_authorization_event(uuid) FROM PUBLIC",
        "GRANT EXECUTE ON FUNCTION identity_activate_tenant_context(bytea, uuid) "
        "TO holospan_tenant_runtime",
        "GRANT EXECUTE ON FUNCTION identity_current_tenant_id() TO holospan_tenant_runtime",
        "GRANT EXECUTE ON FUNCTION identity_activate_auth_context(bytea), "
        "identity_current_auth_claims(), identity_current_auth_principal_id(), "
        "identity_auth_is_platform_admin(), identity_auth_has_tenant(uuid), "
        "identity_auth_has_membership(uuid) TO holospan_auth_runtime",
        "GRANT EXECUTE ON FUNCTION identity_seal_authorization_event(uuid) "
        "TO holospan_audit_writer",
        "GRANT SELECT, INSERT, UPDATE ON identity_principals, identity_browser_sessions "
        "TO holospan_auth_runtime",
        "GRANT SELECT, INSERT ON identity_tenants, identity_memberships, "
        "identity_membership_roles TO holospan_auth_runtime",
        "GRANT SELECT ON identity_tenant_roles, identity_tenant_permissions, "
        "identity_tenant_role_permissions, identity_platform_roles, "
        "identity_platform_permissions, identity_platform_role_permissions "
        "TO holospan_auth_runtime",
        "GRANT SELECT, INSERT ON identity_principal_platform_roles TO holospan_auth_runtime",
        "GRANT INSERT ON identity_authorization_audit_outbox TO holospan_auth_runtime",
        "GRANT SELECT ON identity_principals, identity_tenant_roles, "
        "identity_tenant_permissions, identity_tenant_role_permissions, identity_tenants, "
        "identity_memberships, identity_membership_roles, identity_authorization_audit_outbox "
        "TO holospan_tenant_runtime",
        "GRANT INSERT, DELETE ON identity_membership_roles TO holospan_tenant_runtime",
        "GRANT INSERT ON identity_authorization_audit_outbox TO holospan_tenant_runtime",
        "REVOKE INSERT, UPDATE, DELETE ON identity_sealed_authorization_audit_events "
        "FROM holospan_audit_writer",
    )
    for grant in grants:
        op.execute(grant)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS identity_seal_authorization_event(uuid)")
    op.execute("DROP FUNCTION IF EXISTS identity_current_tenant_id() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_activate_tenant_context(bytea, uuid)")
    op.execute("DROP FUNCTION IF EXISTS identity_auth_has_membership(uuid) CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_auth_has_tenant(uuid) CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_auth_is_platform_admin() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_current_auth_principal_id() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_current_auth_claims() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_activate_auth_context(bytea)")
    op.execute("DROP FUNCTION IF EXISTS identity_preserve_tenant_admin() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_preserve_active_admin_membership() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_protect_canonical_tenant_admin_role() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS identity_validate_membership_role_scope() CASCADE")
    for table in (
        "identity_rls_signing_keys",
        "identity_sealed_authorization_audit_events",
        "identity_authorization_audit_outbox",
        "identity_browser_sessions",
        "identity_principal_platform_roles",
        "identity_platform_role_permissions",
        "identity_platform_permissions",
        "identity_platform_roles",
        "identity_membership_roles",
        "identity_tenant_role_permissions",
        "identity_tenant_permissions",
        "identity_tenant_roles",
        "identity_memberships",
        "identity_tenants",
        "identity_principals",
    ):
        op.drop_table(table)
    for enum_name in (
        "identity_audit_outcome",
        "identity_session_plane",
        "membership_record_status",
        "tenant_record_status",
        "identity_record_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
