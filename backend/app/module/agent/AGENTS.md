# Agent Module — Agent Guide

The agent slice owns the persistent archive agent: an append-only transcript, durable run state, deterministic context projection, validated tools, SSE streaming, human approval, compaction, retry, forking, runtime settings, system prompts, and saved questions.

## Purpose

Keep one conversation resumable and auditable across model steps and process restarts. Provider payloads and UI payloads are separate; every turn is a durable operation, not an in-memory chat array.

## Architecture

- `model/agent_model.py` defines `agent_conversation`, immutable `agent_entry`, operational `agent_run`, and durable `agent_approval`. `agent_config` stores the singleton runtime limits; `saved_question` and `system_prompt_section` live in their own modules.
- Entries use kinds `pi.system`, `pi.user`, `pi.assistant`, `pi.tool-result`, `pi.page-context`, `pi.compaction`, `pi.reset`, and `ui.notice`. `model` is exactly the provider-facing messages; `data` is UI/telemetry and is never sent to the provider.
- The transcript is append-only. Corrections are new boundary entries, context `edits`, or `head_entry_id` changes on a new entry, never updates or deletes of `agent_entry`. One transaction reserves one `agent_commit_seq`, shared by all entries written together.
- `AgentRepository` owns its own short sessions and row locks. This lets an SSE response outlive a request session. Runs move through `running`, `waiting`, `completed`, `failed`, and `cancelled`; only one `running` or `waiting` run may exist per conversation, and request ids are idempotent.
- `begin_message` locks the conversation, rejects an active run, resolves the request id, appends any auto-compaction, an optional page-context snapshot, and the user entry in one transaction, then creates the running run.
- `begin_retry` creates a new run for the latest `failed` or `cancelled` user entry. It does not duplicate the user message; a completed run is not retryable.
- `AgentRuntimeConfig` is an immutable per-request snapshot. It is loaded in a short-lived session before the stream starts; an active stream keeps its snapshot while later runs see new settings. Provider/model selection stays in `AiRuntime`.
- `domain/context_domain.py` deterministically projects entries into a provider request: newest `head_entry_id` selects the active segment; edits are applied; the frozen system/tool snapshot is retained; tool results follow their assistant call; missing results are synthesized; orphan results and failed assistant attempts are excluded.
- Current-time metadata is appended after the user text by the context projection. Page-context snapshots are append-only and deduped by key within the active segment. Compaction/reset boundaries start a new active segment and KV-cache lineage without rewriting earlier rows.
- `AgentService._run_loop` is bounded by the snapshot's step, token, tool-call, parallel, and per-result character limits. Parallel eligible calls run through `asyncio.gather` with a semaphore; persistence and emitted `tool_end` events still follow assistant call order.
- `service/tool_registry.py` validates arguments with Pydantic, dispatches the nine tools, clips each provider-facing result, and turns expected failures into structured `pi.tool-result` errors. A tool failure must not become an HTTP 500 or crash the turn.
- Each tool call gets a separate database session through `_ToolServiceScope`. The tool layer sees knowledge/web-research protocols assembled in `dependencies.py`, not a long-lived request session.
- Tool results carry UI-only `data` (bounded excerpts, viewer descriptors, durations, arguments). Provider content is XML wrapped in a `<tool_result>` envelope; never feed UI data to the model.
- `save_memory` is the only confirmation-required tool. With `save_memory_requires_approval` on, validated arguments create durable approval rows, the run becomes `waiting`, and no tool result exists until an explicit approve/reject. With it off, only the backend authorizes execution. Model-supplied `user_confirmed` never authorizes a write.
- Approval resolution claims the row once, requires earliest-pending order, appends the real result (or `memory_rejected`), and resumes the stored loop snapshot. Startup fails stale `running` runs as `interrupted` and waiting runs without a pending approval as `approval_orphaned`.
- Messages and retry endpoints return `text/event-stream` unless `Accept: application/json` is sent. Event names are `run_start`, `message_start`, `message_delta`, `message_end`, `tool_start`, `tool_end`, `approval_required`, `run_end`, and `error`. Assistant deltas are transport-only; the assistant entry is persisted at `message_end`. SSE headers disable buffering and cache transforms.
- Conversation creation freezes one `pi.system` entry containing ordered prompt sections, the signed-in account's profile, the complete tool snapshot, and prompt/tools versions. Editing prompt rows affects only new conversations.
- Compaction is deterministic and never calls the provider: it builds a bounded `<compaction>` message with a self head. Clear appends a self-headed `pi.reset`; both preserve the full transcript. Fork copies entries through an inclusive cutoff, remaps head/edits, and copies no runs or approvals.
- Saved questions are a separate Q&A surface. CRUD does not require a configured chat provider; `ask` creates a conversation, runs one turn, and writes the latest answer, citations, status, and error back to the same row.

## Key files

- `service/agent_service.py` — turn loop, streaming events, compaction, retry, approvals, fork orchestration.
- `repository/agent_repository.py` — append-only transactions, locks, commit sequence, run recovery.
- `domain/context_domain.py` — entry-to-provider context replay.
- `domain/compaction_domain.py` — token estimate and deterministic summary boundaries.
- `domain/tool_catalog.py` / `domain/tool_args.py` — frozen tool schemas and validators.
- `service/tool_registry.py` — dispatch, error normalization, result clipping, UI previews.
- `router/conversation_router.py` / `router/approval_router.py` — SSE/JSON transports.
- `dependencies.py` — composition root, config snapshot, short-lived tool sessions, test seams.
- `test/fake_chat_generator.py` — deterministic test fake; this package contains no collected tests.

## Conventions

- Never update or delete an entry to fix history. Append a new entry, boundary, edit, or run state change. Preserve `commit_seq` grouping.
- Keep provider `model` and UI `data` separate. If the model should see new content, put it in `model`; if only the inspector needs it, put it in `data`.
- Do not hold the request database session in the loop, tool execution, or stream generator. Open short sessions for appends and tool calls.
- Preserve SSE event names, payload fields, and ordering. Add new event fields compatibly; do not persist incremental assistant deltas.
- Add tools only with a validated argument model, catalog entry, registry dispatcher, and prompt/tools version decision. Bump `PROMPT_VERSION` or `TOOLS_VERSION` when the frozen prefix changes; existing conversations must stay frozen.
- Fail closed on provider/tool errors. Use safe codes and bounded details; never expose raw provider bodies, keys, SQL, or stack traces.
- Enforce approval through the backend `approved` flag. Never let model arguments, route input, or UI state bypass the durable approval row.
- Treat runtime limits as data, not constants. Read them from the immutable snapshot; do not add hidden per-module caps that contradict `agent_config`.
- When changing API schemas or models, update the Alembic revision and regenerate the OpenAPI/Orval client together.
- Put integration coverage in `backend/tests/test_agent.py` (plus the settings/prompt tests). Use `FakeChatGenerator` through `app.state.agent_chat_generator`; do not call a real provider.

## Verification

```bash
cd backend
uv run ruff check app/module/agent tests/test_agent.py
uv run mypy app
PYTHONUNBUFFERED=1 uv run pytest -q tests/test_agent.py
uv run pytest -q tests/test_system_prompt.py tests/test_errors.py
```

Run the full suite when changing context replay, tool behavior, persistence, or SSE contracts. Do not test against a live archive database.

## Related guides

- [Parent](../../AGENTS.md)
- [Knowledge slice](../knowledge/AGENTS.md)
- [Backend tests](../../../tests/AGENTS.md)
