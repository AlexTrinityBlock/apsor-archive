import type { QueryClient } from "@tanstack/react-query";

import {
  getGetAiStatusQueryKey,
  getGetHealthQueryKey,
  getGetProviderRegistryQueryKey,
  getGetStatsQueryKey,
} from "../../generated-apis-types";

/**
 * Refresh every surface that reads provider configuration.
 *
 * These are path-prefix keys, so no parameter variants are left stale. The
 * previous settings page followed this with a blanket `invalidateQueries()`;
 * that is deliberately not used outside seeding.
 */
export async function invalidateProviderQueries(
  queryClient: QueryClient,
): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: getGetProviderRegistryQueryKey(),
    }),
    queryClient.invalidateQueries({ queryKey: getGetAiStatusQueryKey() }),
    queryClient.invalidateQueries({ queryKey: getGetHealthQueryKey() }),
    queryClient.invalidateQueries({ queryKey: getGetStatsQueryKey() }),
  ]);
}

/** Refresh the provider and AI surfaces after re-embedding the corpus. */
export async function invalidateReindexQueries(
  queryClient: QueryClient,
): Promise<void> {
  await invalidateProviderQueries(queryClient);
}
