# Apsor Archive — Agent Guide

Apsor Archive is a local-first, private family/small-team knowledge and memory archive for files, memories, their lineage, and grounded AI answers. One root account manages membership and global runtime settings; every account has its own private archive. This file is the repository-wide orientation and guardrail sheet; product behavior and API detail belong in the READMEs.

## Purpose

Use this guide to choose the right subsystem, respect cross-cutting invariants, and run the repository gates. Detailed backend rules live in `backend/AGENTS.md`; frontend rules live in `frontend/AGENTS.md`.

## Working with a coding agent

`docs/plan/` and `.agents/` are local-only working directories. Both are gitignored and absent from a fresh clone, so no contributor needs them. The parts that matter are the architecture below, the conventions that keep the account boundary and the committed client intact, and the verification gates at the end of this file.

## Architecture

- `backend/` is a Python 3.13 FastAPI service. It owns authentication, account management, per-account file and memory ingestion, hybrid retrieval, provider settings, durable ingestion jobs, and the persistent agent. PostgreSQL 17 is the source of truth; Valkey is a disposable cache; original bytes live under the configured data directory or in the private Cloudflare R2 bucket selected by `APSOR_STORAGE_BACKEND`.
- Every private row carries `user_id`. Request transactions and scoped worker work run as the non-login `apsor_app` role with transaction-local `app.user_id` / `app.user_role` settings, and PostgreSQL row-level security is default-deny. A worker may use a privileged maintenance session only to claim or recover jobs across accounts, then switches to the job owner's context. Root manages accounts and global config but is not a data superuser and must not read another account's archive through normal API queries. Explicit impersonation is the deliberate trusted exception: root starts a marked target session, the target's role drives authorization, and returning to root requires the root password.
- Authentication tables (`app_user`, `user_session`) are deliberately outside RLS because login and session lookup happen before a user context exists. Global config tables are read-all/root-write; private tables use owner-only policies.
- `frontend/` is a React 19 + TypeScript + Vite SPA. It uses React Query for server state and a committed Orval client generated from `frontend/openapi.json`. The production build is committed under `frontend/dist`.
- FastAPI serves the SPA and `/api/v1` from the same origin. API routes win before the SPA fallback. The container image copies the committed client; it does not run a frontend build.
- Root deployment files are `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.cloudflare-tunnel.yml`, and `docker/caddy/`. The production Compose files run separate API and ingestion-worker services; only the worker drains ingestion jobs.
- `docs/cloudflare-tunnel.md` is the deployment/security guide; `secrets/README.md` documents local secret-file handling. `Makefile` and `start.sh` are the supported local command paths.
- A normal request path is router → service → repository. Cross-cutting resources are created in the app lifespan and exposed through `app.state`; each vertical slice assembles its own dependencies.
- A durable ingestion job and an agent run are separate asynchronous workflows. Neither workflow may hold a request-scoped database session for its full lifetime.

## Key files

- `README.md` — product behavior, feature surface, and operator-facing setup.
- `Makefile` — canonical lint, test, build, API-contract, and Compose commands.
- `backend/AGENTS.md` — backend service rules and verification.
- `frontend/AGENTS.md` — frontend architecture, generated-client, and UI rules.
- `Dockerfile` / `docker-compose*.yml` — production, dev-dependency, and tunnel runtimes.
- `.env.example` / `secrets/README.md` — configuration names and secret-file expectations.

## Conventions

- **Do not hand-edit generated API artifacts.** Backend route/schema changes must regenerate `frontend/openapi.json` and `frontend/src/app/generated-apis-types/` through `make api-export` and `make api-generate`. `make api-check` is the staleness gate. Keep operation IDs stable unless the contract intentionally changes.
- **The committed client is part of the deliverable.** `frontend/dist/` (including `dist/pdfjs/`) is tracked because Docker serves it and never builds it. After frontend changes, rebuild and commit `frontend/dist/`; regenerate and commit the Orval output only when the backend contract changes.
- **Schema changes are migration changes.** Update the SQLAlchemy models, add an Alembic revision, and validate upgrade/downgrade against a development PostgreSQL database. The test suite runs the Alembic chain, including RLS role/grants/policies, but it does not replace a downgrade check.
- **Ownership is part of the schema.** A new private table needs `user_id`, owner-safe composite foreign keys where it references a parent, an RLS policy, grants for `apsor_app`, and an entry in the test fixture's table classification (truncation is derived from the catalog). A new global config table needs read-all/root-write policies. Never expose private rows through an unauthenticated or cross-account query.
- **Never commit credentials or archive bytes.** `.env*` (except `.env.example`), `.secrets/` (including `.secrets/r2.env`), `secrets/*` (except its README), `backend/data/`, and local archives are ignored. Database-stored provider keys are encrypted at rest and must never be logged, returned in plaintext, or placed in URLs. R2 credentials are mounted read-only and never become container environment variables.
- **Keep the validation envelope stable.** Request validation is normalized by the backend to `400 invalid_request`; domain failures use the shared `{status, error, detail}` envelope with stable machine-readable `error` codes.
- **Respect the account boundary.** The supported product is one local deployment with exactly one root and any number of normal accounts, each with one private archive. Do not add tenants, workspaces, memberships, shared archives, or per-user provider keys without an explicit product change. Root account management is not a data-access grant, but password reset and explicit impersonation are trusted-recovery capabilities that can transfer sign-in access; impersonation is visible, uses a marked target session, and requires the root password to end. Treat root as the highest-trust credential and never describe RLS as protection against a malicious root.
- **Archive content is not UI copy.** Frontend UI strings exist in English, Traditional Chinese, and Simplified Chinese; user content, file names, citations, raw URLs, and model output are never translated. Run `bun run i18n:check` after locale changes.
- **Keep tests offline and isolated.** Provider tests use injected fakes. Never call DeepSeek, OpenAI, Tavily, or a live archive database from tests.
- **For documentation-only work, do not start services or run builds merely to validate prose.** Use static checks such as `git diff --check` for docs changes.

## Verification

```bash
# Repository gates (require the documented local dependencies)
make lint
make test
make api-check

# Build the client that Docker will serve
make build
```

`make test` uses the development PostgreSQL and a disposable test database; it must never point at a live archive. For docs-only changes, verify with `git diff --check` and confirm the intended file set with `git status --short`.

## Related guides

- [Backend](./backend/AGENTS.md)
- [Frontend](./frontend/AGENTS.md)
