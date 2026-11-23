FROM ghcr.io/astral-sh/uv:0.13.4 AS uv

FROM python:3.13.9-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.13.9-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src:/app/agent-src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 holospan \
    && useradd --system --uid 10001 --gid holospan --home-dir /nonexistent --shell /usr/sbin/nologin holospan
WORKDIR /app
COPY --from=builder --chown=holospan:holospan /app/.venv /app/.venv
COPY --chown=holospan:holospan backend/src ./src
COPY --chown=holospan:holospan agent/holospan_assurance/src ./agent-src
COPY --chown=holospan:holospan backend/alembic ./alembic
COPY --chown=holospan:holospan backend/alembic.ini ./alembic.ini
USER holospan
EXPOSE 8000
CMD ["uvicorn", "holospan_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
