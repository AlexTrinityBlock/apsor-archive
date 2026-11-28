import { lazy, Suspense } from "react";
import { Navigate, useLocation } from "react-router-dom";

import "./library.css";
import "../viewer/viewer.css";

import {
  legacyLibraryRedirect,
  parseLibraryMemoryUrl,
  parseLibraryUrl,
} from "../../lib/library-url";
import { LibraryBrowser } from "./LibraryBrowser";
import { RouteFallback } from "../component/RouteFallback";

const LibraryMemoryWorkspace = lazy(() =>
  import("./memory/LibraryMemoryWorkspace").then((module) => ({
    default: module.LibraryMemoryWorkspace,
  })),
);

/**
 * Canonical entry point. Old query-string Library links are redirected before
 * the browser state hooks mount so saved citations and history entries keep
 * working after the REST URL migration.
 */
export function LibraryPage() {
  const location = useLocation();
  const legacy = legacyLibraryRedirect(location.pathname, location.search);
  if (legacy) {
    return <Navigate to={legacy.to} state={legacy.state} replace />;
  }
  const memoryRoute = parseLibraryMemoryUrl(location.pathname);
  if (memoryRoute !== null) {
    return (
      <Suspense fallback={<RouteFallback />}>
        <LibraryMemoryWorkspace route={memoryRoute} />
      </Suspense>
    );
  }
  const route = parseLibraryUrl(location.pathname);
  if (route === null) {
    return <Navigate to="/library" replace />;
  }
  return <LibraryBrowser route={route} />;
}
