SHELL := /usr/bin/env bash

.PHONY: install lint test build up down logs smoke local-idp-up local-idp-credentials security-sast security-dast security-all

install:
	cd frontend && npm ci
	cd backend && uv sync --frozen

lint:
	cd frontend && npm run lint && npm run typecheck
	cd backend && uv run ruff check . && uv run mypy src

test:
	cd frontend && npm test -- --run
	cd backend && uv run pytest

build:
	cd frontend && npm run build
	docker compose build frontend backend

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

smoke:
	curl --fail --silent http://127.0.0.1:8080/healthz
	curl --fail --silent http://127.0.0.1:8080/api/v1/health/readiness

local-idp-up:
	./scripts/local/keycloak.sh up

local-idp-credentials:
	./scripts/local/keycloak.sh credentials

security-sast:
	./scripts/security/sast.sh

security-dast:
	./scripts/security/dast.sh

security-all: security-sast security-dast
