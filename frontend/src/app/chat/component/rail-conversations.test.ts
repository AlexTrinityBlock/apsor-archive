// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import type {
  AgentConversationSchema,
  AgentConversationSchemaStatus,
} from "../../generated-apis-types/schemas";
import { visibleConversations } from "./rail-conversations";

/** Minimal conversation metadata; the filter only reads `id` and `status`. */
function conversation(
  id: number,
  status: AgentConversationSchemaStatus,
): AgentConversationSchema {
  return {
    archived_at: status === "archived" ? "2026-01-01T00:00:00Z" : null,
    created_at: "2026-01-01T00:00:00Z",
    deleted_at: null,
    fork_at_entry_id: null,
    id,
    last_entry_at: null,
    model: "mock",
    parent_conversation_id: null,
    provider: "mock",
    provider_session_id: `session-${id}`,
    status,
    title: `Conversation ${id}`,
    updated_at: "2026-01-01T00:00:00Z",
  };
}

test("keeps only active conversations", () => {
  const rows = [
    conversation(1, "active"),
    conversation(2, "archived"),
    conversation(3, "active"),
  ];

  expect(visibleConversations(rows, new Set()).map((row) => row.id)).toEqual([
    1, 3,
  ]);
});

test("keeps a just-deleted conversation hidden until the refetch drops it", () => {
  const rows = [conversation(1, "active"), conversation(2, "active")];

  expect(
    visibleConversations(rows, new Set([2])).map((row) => row.id),
  ).toEqual([1]);
});

test("an empty removedIds set leaves the list untouched", () => {
  const rows = [conversation(7, "active")];

  expect(visibleConversations(rows, new Set())).toHaveLength(1);
  expect(visibleConversations([], new Set([7]))).toHaveLength(0);
});
