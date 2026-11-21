# Holospan backend

The backend is a FastAPI modular monolith organized by **business capability**,
not by global technical layers. A capability owns its contracts, use cases,
persistence adapters and HTTP surface.

```text
backend/
├── alembic/                         # versioned database migrations
├── src/holospan_api/
│   ├── core/                        # cross-cutting runtime mechanisms only
│   ├── platform/                    # technical health and operations
│   └── domains/
│       └── system_catalog/          # first implemented business capability
└── tests/
    ├── platform/
    └── system_catalog/
```

Planned domain boundaries are documented in `domains/README.md`. They become
packages only when their contract and first vertical use case are implemented.
Avoid global `models/`, `crud/`, `routers/`, or `schemas/` directories: those
create coupling by technical concern and make domain ownership unclear.

## Local commands

```bash
uv sync --frozen
uv run ruff check .
uv run mypy src
uv run pytest
uv run alembic upgrade head
uv run uvicorn holospan_api.main:app --reload
```
