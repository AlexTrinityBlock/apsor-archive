import { useQueryClient } from "@tanstack/react-query";

const ADMIN_PREFIX = "/api/v1/admin/companions";

/**
 * Refetch every root companion query after a change. Admin views are small and
 * root-only, so a broad invalidation keeps every panel consistent without
 * tracking which panel depends on which row.
 */
export function useAdminRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({
      predicate: (query) =>
        typeof query.queryKey[0] === "string" &&
        query.queryKey[0].startsWith(ADMIN_PREFIX),
    });
  };
}

/** Display name for a companion ref when no richer label is available. */
export function refLabel(
  ref: string,
  names: ReadonlyMap<string, string>,
): string {
  return names.get(ref) ?? ref.replace(/^preset:/, "").replace(/^custom:/, "#");
}
