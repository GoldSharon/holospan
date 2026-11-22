#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
reports="$repo_root/security/reports"
mkdir -p "$reports"
cd "$repo_root"

compose_args=()
if [[ -f "$repo_root/.env.local-idp" ]]; then
  compose_args+=(
    --env-file "$repo_root/.env.local-idp"
    -f "$repo_root/compose.yaml"
    -f "$repo_root/compose.local-idp.yaml"
  )
fi

docker compose "${compose_args[@]}" up --build -d postgres backend frontend

ready=0
for _ in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8080/api/v1/health/readiness >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  docker compose "${compose_args[@]}" logs --tail=200 frontend backend postgres
  exit 1
fi

docker run --rm --network holospan_edge -v "$reports:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:2.17.0 zap-baseline.py \
  -t http://frontend:8080 -m 3 -I -J zap-web.json -r zap-web.html

docker run --rm --network holospan_edge -v "$reports:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:2.17.0 zap-api-scan.py \
  -t http://backend:8000/openapi.json -f openapi -I -J zap-api.json -r zap-api.html
