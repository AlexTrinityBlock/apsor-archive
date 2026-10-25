import type { QueryClient } from "@tanstack/react-query";

/**
 * Refresh every surface that can show a memory after an edit or deprecation.
 *
 * The generated query keys all start with their API path, so the prefixes below
 * cover list, read, search, timeline, and aggregate stats without enumerating
 * individual parameter combinations. Conversation transcripts are deliberately
 * excluded: their citation labels and tool results are frozen history.
 */
export async function invalidateMemorySurfaces(queryClient: QueryClient): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["/api/v1/memories"] }),
    queryClient.invalidateQueries({ queryKey: ["/api/v1/search"] }),
    queryClient.invalidateQueries({ queryKey: ["/api/v1/timeline"] }),
    queryClient.invalidateQueries({ queryKey: ["/api/v1/stats"] }),
  ]);
}
