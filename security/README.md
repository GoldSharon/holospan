# Security gates

The repository owner authorizes these tests only against local, development,
or explicitly approved Holospan environments. They must not be pointed at a
third-party or production target without a separate written scope.

## SAST and supply-chain gate

Run `make security-sast`. It uses exact tool-image versions and blocks on:

- Semgrep findings configured as errors;
- detected secrets;
- Trivy high/critical dependency or configuration findings;
- npm high/critical advisories;
- Python vulnerability advisories;
- ESLint, Bandit, Ruff or mypy failures; or
- unit-test failures.

## DAST gate

Run `make security-dast`. It builds the pinned frontend/backend/PostgreSQL
profile, waits for readiness, then runs OWASP ZAP baseline web and OpenAPI scans.
Reports are written to `security/reports/` and are intentionally not committed.

The first scan is a baseline, not proof of security. Authentication,
authorization, tenant isolation, rate limits, uploads, agent tools, and
effectful workflows require targeted tests as those features are implemented.
