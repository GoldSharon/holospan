#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

docker run --rm -v "$repo_root:/src:ro" -w /src semgrep/semgrep:1.145.2 \
  semgrep scan --no-git-ignore --config p/python --config p/typescript \
  --config p/owasp-top-ten --error backend/src frontend/src

docker run --rm -v "$repo_root:/repo:ro" zricethezav/gitleaks:v8.30.0 \
  detect --source /repo --no-git --config /repo/.gitleaks.toml --redact --exit-code 1

docker run --rm -v "$repo_root:/repo:ro" aquasec/trivy:0.68.2 \
  fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --exit-code 1 /repo

(
  cd frontend
  npm ci
  npm audit --audit-level=high
  npm run lint
  npm run typecheck
  npm test -- --run
)

(
  cd backend
  uv sync --frozen
  uv run pip-audit
  uv run bandit -q -r src
  uv run ruff check .
  uv run mypy src
  uv run pytest
)
