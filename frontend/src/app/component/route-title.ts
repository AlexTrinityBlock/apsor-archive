/**
 * Route helpers for the application shell: which workspace a path belongs
 * to, and which navigation label names it.
 */

/** The first path segment, e.g. `/library/files/3` → `library`. */
export function workspaceSegment(pathname: string): string {
  return pathname.split("/").find((segment) => segment.length > 0) ?? "";
}

interface TitledRoute<K> {
  readonly to: string;
  readonly labelKey: K;
}

/**
 * The label of the navigation entry that owns `pathname`: an exact match or
 * the longest `to` prefix that ends on a segment boundary.
 */
export function routeLabelKey<K>(
  pathname: string,
  routes: readonly TitledRoute<K>[],
): K | null {
  let best: TitledRoute<K> | null = null;
  for (const route of routes) {
    const matches =
      pathname === route.to || pathname.startsWith(`${route.to}/`);
    if (matches && (best === null || route.to.length > best.to.length)) {
      best = route;
    }
  }
  return best?.labelKey ?? null;
}
