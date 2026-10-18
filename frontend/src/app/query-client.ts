import { QueryClient } from "@tanstack/react-query";

/**
 * Shared React Query client.
 *
 * Mutations in later page work should invalidate the keys that feed the
 * overview, search, timeline, tree, and library views. The defaults below keep
 * a local-first app responsive without hiding real API failures.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
