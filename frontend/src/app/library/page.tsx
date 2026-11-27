import { Navigate, useLocation } from "react-router-dom";

import "./library.css";
import "../viewer/viewer.css";

import {
  legacyLibraryRedirect,
  parseLibraryUrl,
} from "../../lib/library-url";
import { LibraryBrowser } from "./LibraryBrowser";

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
  const route = parseLibraryUrl(location.pathname);
  if (route === null) {
    return <Navigate to="/library" replace />;
  }
  return <LibraryBrowser route={route} />;
}
