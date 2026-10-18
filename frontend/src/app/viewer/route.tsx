/**
 * Route-ready exports for the standalone resource viewer.
 *
 * Integration (the main agent owns `router.tsx`):
 *
 * ```tsx
 * const ViewerPage = lazy(loadViewerPage);
 * ```
 *
 * Place these three routes under `AuthGate` as siblings of the `AppShell`
 * route, not as children of it:
 *
 * ```tsx
 * { path: "viewer/file/:fileId", element: <ViewerPage /> },
 * { path: "viewer/media/:mediaId", element: <ViewerPage /> },
 * { path: "viewer/memory/:memoryId", element: <ViewerPage /> },
 * ```
 *
 * The viewer supplies its own top bar, Suspense boundary, safe-area padding,
 * dark-mode styling, and full-screen stage, so wrapping it in `AppShell`
 * would duplicate chrome and mobile tabs.
 */
import type { ComponentType } from "react";

/** Lazy loader for the route element; keeps PDF/DOCX engines out of the shell. */
export function loadViewerPage(): Promise<{ default: ComponentType }> {
  return import("./page").then((module) => ({ default: module.ViewerPage }));
}

/** The three viewer paths, exported for route tables and link builders. */
export const VIEWER_ROUTE_PATHS = [
  "viewer/file/:fileId",
  "viewer/media/:mediaId",
  "viewer/memory/:memoryId",
] as const;
