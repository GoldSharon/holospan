#!/bin/sh
set -eu

psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=auth_user="$HOLOSPAN_AUTH_DB_USER" \
  --set=auth_password="$HOLOSPAN_AUTH_DB_PASSWORD" \
  --set=tenant_user="$HOLOSPAN_TENANT_DB_USER" \
  --set=tenant_password="$HOLOSPAN_TENANT_DB_PASSWORD" \
  --set=audit_user="$HOLOSPAN_AUDIT_DB_USER" \
  --set=audit_password="$HOLOSPAN_AUDIT_DB_PASSWORD" <<'SQL'
CREATE ROLE holospan_auth_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE holospan_tenant_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE holospan_audit_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT',
  :'auth_user', :'auth_password'
) \gexec
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT',
  :'tenant_user', :'tenant_password'
) \gexec
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT',
  :'audit_user', :'audit_password'
) \gexec

SELECT format('GRANT holospan_auth_runtime TO %I', :'auth_user') \gexec
SELECT format('GRANT holospan_tenant_runtime TO %I', :'tenant_user') \gexec
SELECT format('GRANT holospan_audit_writer TO %I', :'audit_user') \gexec
SQL
