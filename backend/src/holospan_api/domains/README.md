# Business domain map

Each directory under `domains/` is a vertical business capability. Domain code
must not import another domain's persistence internals; communication occurs
through explicit application contracts or durable events.

Planned boundaries:

- `identity_access` — identities, tenants, roles, grants, elevation and support access;
- `system_catalog` — systems under assurance, environments and declared capabilities;
- `context_intelligence` — requirements, documents, media, API contracts and lineage;
- `assurance_planning` — risks, controls, coverage and assurance plans;
- `scenario_design` — scenarios, personas, simulations and datasets;
- `execution` — runs, phases, effects, retries, cancellation and handoffs;
- `evaluations` — evaluator definitions, versions, judges, observations and verdicts;
- `telemetry` — source mappings, receipts, trace identity and ingestion state;
- `evidence` — manifests, artifacts, findings, exports and integrity state;
- `governance` — reviews, approvals, waivers, decisions and framework mappings;
- `administration` — tenant administration policies and platform-operator workflows.

Only `system_catalog` is implemented in the initial slice. New domains are
created from an accepted contract and one end-to-end use case, not as empty
folders.
