#!/usr/bin/env bash
set -euo pipefail

postgres_container="${HOLOSPAN_POSTGRES_CONTAINER:-holospan-postgres-1}"
postgres_owner="${HOLOSPAN_POSTGRES_USER:-holospan}"
postgres_database="${HOLOSPAN_POSTGRES_DB:-holospan}"

docker exec -i "$postgres_container" psql \
  --set=ON_ERROR_STOP=1 \
  --username "$postgres_owner" \
  --dbname "$postgres_database" <<'SQL'
BEGIN;
INSERT INTO identity_principals (
  id, issuer, subject, status, last_seen_at, created_at, updated_at, version
) VALUES (
  '11111111-1111-4111-8111-111111111111', 'https://id.test', 'rls-user',
  'ACTIVE', now(), now(), now(), 1
);
INSERT INTO identity_tenants (
  id, slug, display_name, status, created_by, created_at, updated_at, version
) VALUES
  ('22222222-2222-4222-8222-222222222222', 'rls-visible', 'Visible', 'ACTIVE',
   '11111111-1111-4111-8111-111111111111', now(), now(), 1),
  ('33333333-3333-4333-8333-333333333333', 'rls-hidden', 'Hidden', 'ACTIVE',
   '11111111-1111-4111-8111-111111111111', now(), now(), 1);
INSERT INTO identity_memberships (
  id, tenant_id, principal_id, status, created_at, updated_at, version
) VALUES (
  '44444444-4444-4444-8444-444444444444',
  '22222222-2222-4222-8222-222222222222',
  '11111111-1111-4111-8111-111111111111', 'ACTIVE', now(), now(), 1
);
INSERT INTO identity_browser_sessions (
  id, token_digest, csrf_digest, principal_id, plane,
  auth_time, created_at, last_seen_at, expires_at
) VALUES (
  '55555555-5555-4555-8555-555555555555',
  digest('rls-session-token', 'sha256'), digest('csrf', 'sha256'),
  '11111111-1111-4111-8111-111111111111', 'TENANT',
  now(), now(), now(), now() + interval '1 hour'
);
INSERT INTO identity_membership_roles (membership_id, role_id, tenant_id)
VALUES (
  '44444444-4444-4444-8444-444444444444',
  '044ac191-98c7-45ef-8d40-e5cda2dedf6e',
  '22222222-2222-4222-8222-222222222222'
);

SET LOCAL ROLE holospan_auth_runtime;
SELECT 1 / (count(*) = 0)::int FROM identity_tenants;
SELECT set_config(
  'app.holospan_auth_context',
  '11111111-1111-4111-8111-111111111111|TENANT|9999999999|forged',
  true
);
SELECT 1 / (count(*) = 0)::int FROM identity_tenants;
SELECT identity_activate_auth_context(digest('rls-session-token', 'sha256'));
SELECT 1 / (
  count(*) = 1 AND min(slug) = 'rls-visible'
)::int FROM identity_tenants;
RESET ROLE;

SET LOCAL ROLE holospan_tenant_runtime;
SELECT 1 / (count(*) = 0)::int FROM identity_tenants;
SELECT set_config(
  'app.holospan_context',
  '22222222-2222-4222-8222-222222222222|11111111-1111-4111-8111-111111111111|9999999999|forged',
  true
);
SELECT 1 / (count(*) = 0)::int FROM identity_tenants;
SELECT identity_activate_tenant_context(
  digest('rls-session-token', 'sha256'),
  '22222222-2222-4222-8222-222222222222'
);
SELECT 1 / (
  count(*) = 1 AND min(slug) = 'rls-visible'
)::int FROM identity_tenants;
RESET ROLE;
DO $$
BEGIN
  BEGIN
    UPDATE identity_memberships SET status = 'SUSPENDED'
    WHERE id = '44444444-4444-4444-8444-444444444444';
    RAISE EXCEPTION 'final administrator suspension unexpectedly succeeded';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    UPDATE identity_tenant_roles SET key = 'renamed_admin'
    WHERE id = '044ac191-98c7-45ef-8d40-e5cda2dedf6e';
    RAISE EXCEPTION 'canonical tenant administrator mutation unexpectedly succeeded';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
END $$;
ROLLBACK;

BEGIN;
INSERT INTO identity_principals (
  id, issuer, subject, status, last_seen_at, created_at, updated_at, version
) VALUES (
  '11111111-1111-4111-8111-111111111111', 'https://id.test', 'audit-user',
  'ACTIVE', now(), now(), now(), 1
);
INSERT INTO identity_authorization_audit_outbox (
  id, stream, actor_principal_id, action, outcome, reason_code, request_id,
  principal_type, session_type, policy_version, metadata, occurred_at
) VALUES (
  '66666666-6666-4666-8666-666666666666', 'platform',
  '11111111-1111-4111-8111-111111111111', 'platform.test', 'SUCCEEDED',
  'TEST', 'test-request', 'human', 'platform', 'identity-access-v1', '{}', now()
);
SET LOCAL ROLE holospan_audit_writer;
SELECT identity_seal_authorization_event(
  '66666666-6666-4666-8666-666666666666'
);
RESET ROLE;
SELECT 1 / (
  sequence = 1 AND previous_digest IS NULL AND octet_length(event_digest) = 32
  AND sealer_identity = session_user
)::int FROM identity_sealed_authorization_audit_events
WHERE id = '66666666-6666-4666-8666-666666666666';
SELECT 1 / (
  NOT has_table_privilege(
    'holospan_audit_writer',
    'identity_sealed_authorization_audit_events',
    'UPDATE'
  )
)::int;
SELECT 1 / (
  NOT has_table_privilege(
    'holospan_audit_writer',
    'identity_sealed_authorization_audit_events',
    'INSERT'
  )
)::int;
SELECT 1 / (
  NOT has_table_privilege(
    'holospan_auth_runtime', 'identity_membership_roles', 'UPDATE'
  )
  AND NOT has_table_privilege(
    'holospan_auth_runtime', 'identity_membership_roles', 'DELETE'
  )
  AND NOT has_table_privilege(
    'holospan_auth_runtime', 'identity_tenant_roles', 'UPDATE'
  )
  AND NOT has_table_privilege(
    'holospan_auth_runtime', 'identity_authorization_audit_outbox', 'SELECT'
  )
  AND NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = 'holospan_auth_runtime')
)::int;
ROLLBACK;
SQL
