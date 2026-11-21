# Holospan

Holospan is an agentic AI assurance platform for the complete software and AI
lifecycle. It unifies shift-left testing with shift-right observability,
continuous evaluation, red teaming, human and field research, audits, and
bounded formal verification.

Its evaluator layer is open: teams can use built-in metrics, sandboxed code,
LLM-as-judge, JEV-as-judge, private or fine-tuned judge models, remote services,
human review, and formal adapters through one versioned evaluator contract.

Source code is optional. Holospan must also be able to onboard a black-box or
codeless system from BRDs, FRDs, PRDs, architecture and API documentation,
audio/video, screenshots, policies, examples, an invocation endpoint, and
existing traces. If a deployed system already emits OpenTelemetry,
OpenInference, or vendor telemetry, Holospan should consume that evidence
without requiring the customer to reinstrument or disclose its code.

Holospan is not intended to be another trace viewer. Its core is an assurance
graph that links what a system must do, what was tested or observed, the
evidence produced, what remains unknown, and whether a release or production
decision is justified.

## Product promise

For every agent, model, workflow, prompt, tool, retrieval system, and release,
Holospan should answer:

1. What are the requirements, risks, and assurance objectives?
2. What evidence exists across development and production?
3. What passed, failed, or could not be verified?
4. Where are the assurance gaps and highest-risk unknowns?
5. What should be tested, investigated, or remediated next?
6. Is the system ready to release, continue operating, or require human action?

## Five assurance modes

- Technical testing: functional, non-functional, AI-specific, statistical,
  metamorphic, differential, adversarial, and regression testing.
- Red teaming: model, implementation, infrastructure, and runtime attack
  assessment.
- User and field testing: real-user studies, usability, trust calibration,
  automation-bias testing, pilots, feedback, and incident evidence.
- Audits and assessments: impact, bias, compliance, conformity, independent
  review, corrective action, and continuous-control monitoring.
- Formal verification: proofs or counterexamples for explicitly modeled
  policies, state transitions, authorization, data flow, and safety invariants.

## The agentic loop

Holospan continuously connects both sides of the lifecycle:

`requirement/risk -> scenario -> simulation/run -> trace -> evaluation -> evidence -> finding -> remediation -> release gate -> production observation -> regression test`

The platform itself is agentic, but consequential actions remain bounded by
permissions, declared scope, evidence requirements, and human approval gates.

## Design documents

- [Product blueprint](docs/PRODUCT_BLUEPRINT.md)
- [System architecture](docs/architecture/HOLOSPAN_SYSTEM_ARCHITECTURE.md)
- [Ordered architecture package](docs/architecture/README.md)
- [Source-product and standards research](docs/SOURCE_PRODUCT_RESEARCH.md)
- [REA capability-check plan](docs/REA_CAPABILITY_CHECK_PLAN.md)

## Current state

The first implementation foundation is runnable:

- React, TypeScript, Vite and Tailwind frontend;
- FastAPI modular-monolith backend organized by business capability;
- PostgreSQL, ClickHouse, MinIO and Redpanda in a pinned Docker Compose profile;
- Alembic migration infrastructure;
- non-root application containers and private data-service bindings; and
- lint, type, unit, dependency, secret, SAST and DAST gates.

The current UI and API are a validated application shell, not the completed
assurance product. The next domain slice is identity, tenancy and RBAC, followed
by system/context onboarding and durable telemetry acceptance.

## Run locally or on the initial EC2 host

Prerequisites: Docker Engine 29+ with Compose 2.40+, 8 CPU cores, and 32 GB RAM.

```bash
cp .env.example .env
# Replace every placeholder password in .env before starting.
docker compose up --build -d
docker compose ps
```

Open `http://HOST:8080`. Data-service ports bind to loopback; only the frontend
port is public by default. For an internet-facing EC2 deployment, terminate TLS
at an approved reverse proxy or load balancer and restrict the security group.

```bash
make lint
make test
make security-sast
make security-dast
```

All application dependencies and container images use exact versions. Lockfiles
are committed; floating `latest` tags are prohibited.
