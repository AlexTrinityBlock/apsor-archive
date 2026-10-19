/**
 * Scoped React Query invalidations for one conversation.
 *
 * A conversation list key is the API path alone, so invalidating that prefix
 * refreshes every `status`/`limit` variant. Detail and entry keys are nested
 * below the conversation id and are invalidated separately.
 */
import type { QueryClient } from "@tanstack/react-query";

import {
  getGetAgentConversationQueryKey,
  getListAgentApprovalsQueryKey,
  getListAgentConversationsQueryKey,
  getListAgentEntriesQueryKey,
} from "../generated-apis-types/agent/agent";

const CONVERSATION_LIST_KEY = getListAgentConversationsQueryKey();

export function invalidateConversationList(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ queryKey: CONVERSATION_LIST_KEY });
}

export function invalidateConversationDetail(
  client: QueryClient,
  conversationId: number,
): Promise<void> {
  return Promise.all([
    client.invalidateQueries({
      queryKey: getGetAgentConversationQueryKey(conversationId),
    }),
    client.invalidateQueries({
      queryKey: getListAgentEntriesQueryKey(conversationId),
    }),
    client.invalidateQueries({
      queryKey: getListAgentApprovalsQueryKey(conversationId),
    }),
  ]).then(() => undefined);
}

export function invalidateConversation(
  client: QueryClient,
  conversationId: number,
): Promise<void> {
  return Promise.all([
    invalidateConversationList(client),
    invalidateConversationDetail(client, conversationId),
  ]).then(() => undefined);
}
