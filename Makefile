SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c

.PHONY: help setup dev-deps api worker web build test test-api test-web lint audit up down \
	api-export api-generate api-check

help:
	@printf '%s\n' \
	  'make setup        Run the setup wizard (writes .env and secret files)' \
	  'make dev-deps     Start the development dependencies (docker-compose.dev.yml)' \
	  'make api          Run the FastAPI server with reload (enqueues ingestion only)' \
	  'make worker       Run the ingestion worker that drains queued jobs' \
	  'make web          Run the Vite dev server' \
	  'make build        Build the frontend into frontend/dist' \
	  'make test         Run the backend integration suite and frontend unit tests' \
	  'make lint         Run lint, type, architecture, security, and i18n checks (offline)' \
	  'make audit        Audit backend and frontend dependencies (needs network)' \
	  'make up           Build and start the production Compose stack' \
	  'make down         Stop the production Compose stack' \
	  'make api-export   Export OpenAPI to frontend/openapi.json' \
	  'make api-generate Regenerate the committed Orval client' \
	  'make api-check    Fail if the committed contract/client is stale'

setup:
	./setup.sh

dev-deps:
	docker compose -f docker-compose.dev.yml up -d --wait

api:
	cd backend && uv run apsor-archive --reload

worker:
	cd backend && uv run apsor-archive worker

web:
	cd frontend && bun run dev

build:
	cd frontend && bun run build

test: test-api test-web

test-api:
	cd backend && PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/apsor-archive-pytest.log

test-web:
	cd frontend && bun run test

lint:
	cd backend && uv run ruff check . && uv run mypy app script && uv run lint-imports \
	  && PYTHONUTF8=1 uv run bandit -q -r app script -c pyproject.toml
	cd frontend && bun run lint && bun run typecheck && bun run i18n:check \
	  && bun run check:boundaries

audit:
	cd backend && uv run pip-audit
	cd frontend && bun audit

up:
	docker compose up -d --build

down:
	docker compose down

api-export:
	cd backend && uv run python -m script.export_openapi

api-generate:
	cd frontend && bun run api:generate

api-check: api-export api-generate
	git diff --exit-code -- frontend/openapi.json frontend/src/app/generated-apis-types
