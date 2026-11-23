#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${repo_root}/.env.local-idp"
compose_files=(-f "${repo_root}/compose.yaml" -f "${repo_root}/compose.local-idp.yaml")

random_secret() {
  openssl rand -hex 32
}

container_value() {
  local container="$1"
  local key="$2"
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container}" 2>/dev/null \
    | awk -v prefix="${key}=" 'index($0, prefix) == 1 { print substr($0, length(prefix) + 1); exit }'
}

existing_or_random() {
  local container="$1"
  local key="$2"
  local value=""
  value="$(container_value "${container}" "${key}" || true)"
  if [[ -n "${value}" ]]; then
    printf '%s' "${value}"
  else
    random_secret
  fi
}

ensure_env() {
  if [[ ! -f "${env_file}" ]]; then
    local temporary
    temporary="$(mktemp "${repo_root}/.env.local-idp.XXXXXX")"
    chmod 600 "${temporary}"
    {
    printf 'HOLOSPAN_ENV=development\n'
    printf 'HOLOSPAN_POSTGRES_DB=holospan\n'
    printf 'HOLOSPAN_POSTGRES_USER=holospan\n'
    printf 'HOLOSPAN_POSTGRES_PASSWORD=%s\n' "$(existing_or_random holospan-postgres-1 POSTGRES_PASSWORD)"
    printf 'HOLOSPAN_AUTH_DB_USER=holospan_auth\n'
    printf 'HOLOSPAN_AUTH_DB_PASSWORD=%s\n' "$(existing_or_random holospan-postgres-1 HOLOSPAN_AUTH_DB_PASSWORD)"
    printf 'HOLOSPAN_TENANT_DB_USER=holospan_tenant\n'
    printf 'HOLOSPAN_TENANT_DB_PASSWORD=%s\n' "$(existing_or_random holospan-postgres-1 HOLOSPAN_TENANT_DB_PASSWORD)"
    printf 'HOLOSPAN_AUDIT_DB_USER=holospan_audit\n'
    printf 'HOLOSPAN_AUDIT_DB_PASSWORD=%s\n' "$(existing_or_random holospan-postgres-1 HOLOSPAN_AUDIT_DB_PASSWORD)"
    printf 'HOLOSPAN_MINIO_ROOT_USER=holospan-admin\n'
    printf 'HOLOSPAN_MINIO_ROOT_PASSWORD=%s\n' "$(existing_or_random holospan-minio-1 MINIO_ROOT_PASSWORD)"
    printf 'HOLOSPAN_IDENTITY_SESSION_SECRET=%s\n' "$(existing_or_random holospan-backend-1 HOLOSPAN_IDENTITY_SESSION_SECRET)"
    printf 'HOLOSPAN_IDENTITY_COOKIE_SECURE=false\n'
    printf 'HOLOSPAN_TENANT_APP_HOST=localhost\n'
    printf 'HOLOSPAN_PLATFORM_ADMIN_HOST=platform.localhost\n'
    printf 'HOLOSPAN_KEYCLOAK_ADMIN_USERNAME=holospan-local-admin\n'
    printf 'HOLOSPAN_KEYCLOAK_ADMIN_PASSWORD=%s\n' "$(random_secret)"
    printf 'HOLOSPAN_LOCAL_TENANT_CLIENT_SECRET=%s\n' "$(random_secret)"
    printf 'HOLOSPAN_LOCAL_PLATFORM_CLIENT_SECRET=%s\n' "$(random_secret)"
    printf 'HOLOSPAN_LOCAL_USER_USERNAME=holospan-user\n'
    printf 'HOLOSPAN_LOCAL_USER_PASSWORD=%s\n' "$(random_secret)"
    printf 'HOLOSPAN_BOOTSTRAP_PLATFORM_ADMINS=http://localhost:8082/realms/holospan-local|00000000-0000-4000-8000-000000000001\n'
    } >"${temporary}"
    mv "${temporary}" "${env_file}"
  fi

  local minio_user minio_password
  minio_user="$(read_env_value HOLOSPAN_MINIO_ROOT_USER)"
  minio_password="$(read_env_value HOLOSPAN_MINIO_ROOT_PASSWORD)"
  if [[ -z "${minio_user}" ]]; then
    minio_user="holospan-admin"
    printf 'HOLOSPAN_MINIO_ROOT_USER=%s\n' "${minio_user}" >>"${env_file}"
  fi
  if [[ -z "${minio_password}" ]]; then
    minio_password="$(existing_or_random holospan-minio-1 MINIO_ROOT_PASSWORD)"
    printf 'HOLOSPAN_MINIO_ROOT_PASSWORD=%s\n' "${minio_password}" >>"${env_file}"
  fi
  if [[ -z "$(read_env_value HOLOSPAN_OBJECT_STORAGE_ACCESS_KEY)" ]]; then
    printf 'HOLOSPAN_OBJECT_STORAGE_ACCESS_KEY=%s\n' "${minio_user}" >>"${env_file}"
  fi
  if [[ -z "$(read_env_value HOLOSPAN_OBJECT_STORAGE_SECRET_KEY)" ]]; then
    printf 'HOLOSPAN_OBJECT_STORAGE_SECRET_KEY=%s\n' "${minio_password}" >>"${env_file}"
  fi
}

read_env_value() {
  local key="$1"
  awk -v prefix="${key}=" 'index($0, prefix) == 1 { print substr($0, length(prefix) + 1); exit }' "${env_file}"
}

up() {
  ensure_env
  docker compose --env-file "${env_file}" "${compose_files[@]}" up --build -d \
    keycloak migrate backend frontend
  curl --fail --silent --show-error --retry 30 --retry-delay 2 --retry-all-errors \
    http://127.0.0.1:8082/realms/holospan-local/.well-known/openid-configuration \
    >/dev/null
  curl --fail --silent --show-error --retry 20 --retry-delay 2 --retry-all-errors \
    http://127.0.0.1:8080/api/v1/identity-access/oidc-config \
    >/dev/null
  printf 'Holospan local OIDC is ready at http://localhost:8080\n'
  printf 'Run "make local-idp-credentials" to display the local-only login.\n'
}

credentials() {
  ensure_env
  printf 'Holospan URL: http://localhost:8080\n'
  printf 'Username: %s\n' "$(read_env_value HOLOSPAN_LOCAL_USER_USERNAME)"
  printf 'Password: %s\n' "$(read_env_value HOLOSPAN_LOCAL_USER_PASSWORD)"
  printf 'Keycloak admin: http://localhost:8082/admin/\n'
}

case "${1:-up}" in
  up)
    up
    ;;
  credentials)
    credentials
    ;;
  *)
    printf 'Usage: %s [up|credentials]\n' "$0" >&2
    exit 2
    ;;
esac
