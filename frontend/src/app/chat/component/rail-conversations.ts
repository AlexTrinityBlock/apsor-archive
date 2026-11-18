import type { AgentConversationSchema } from "../../generated-apis-types/schemas";

/**
 * Conversations the rail may render.
 *
 * Archived rows are hidden defensively: the API's `archived` status is the
 * soft-delete tag, so a stale or unfiltered list must never bring a deleted
 * conversation back. `removedIds` covers the window between an optimistic
 * delete and the refetch that drops the row.
 */
export function visibleConversations(
  conversations: readonly AgentConversationSchema[],
  removedIds: ReadonlySet<number>,
): AgentConversationSchema[] {
  return conversations.filter(
    (conversation) =>
      conversation.status !== "archived" && !removedIds.has(conversation.id),
  );
}
