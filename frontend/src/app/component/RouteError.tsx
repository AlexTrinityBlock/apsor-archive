import { useEffect } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { Button } from "./Button";
import { TreeMark } from "./TreeMark";
import { TreeRings } from "./TreeRings";
import "./route-error.css";

const RELOAD_GUARD_KEY = "dendromatrix.route-error.reload-at";
const CHUNK_ERROR_PATTERN =
  /failed to fetch dynamically imported module|importing a module script failed|chunkloaderror|loading chunk/i;

/** True when a lazy route chunk vanished after a new deployment. */
function isChunkError(error: unknown): boolean {
  if (error instanceof Error) {
    return CHUNK_ERROR_PATTERN.test(error.message);
  }
  return typeof error === "string" && CHUNK_ERROR_PATTERN.test(error);
}

function errorDetail(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    return `${error.status} ${error.statusText}`.trim();
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "The archive could not open this view.";
}

/**
 * Root route error boundary. A stale lazy chunk reloads once so the browser
 * picks up the new index.html; persistent or unrelated errors get a real page
 * instead of React Router's default "Unexpected Application Error" screen.
 */
export function RouteError() {
  const error = useRouteError();
  const chunkError = isChunkError(error);

  useEffect(() => {
    if (!chunkError) {
      return;
    }
    try {
      const lastReload = Number(window.sessionStorage.getItem(RELOAD_GUARD_KEY) ?? "0");
      if (Date.now() - lastReload > 15_000) {
        window.sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()));
        window.location.reload();
      }
    } catch {
      // Storage can be blocked; the manual reload button still works.
    }
  }, [chunkError]);

  return (
    <main className="route-error">
      <div className="route-error__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>
      <section className="route-error__card" role="alert">
        <span className="route-error__mark" aria-hidden="true">
          <TreeMark size={30} />
        </span>
        <p className="eyebrow">Archive · route error</p>
        <h1>{chunkError ? "A newer build is ready." : "The archive could not open this view."}</h1>
        <p className="route-error__description">
          {chunkError
            ? "Reload to collect the current build. This usually happens right after a deployment while an older tab is still open."
            : "The page stopped before it could render. Your files and memories are unchanged."}
        </p>
        <div className="route-error__actions">
          <Button variant="primary" onClick={() => window.location.reload()}>
            Reload archive
          </Button>
          <a className="btn btn--secondary btn--md" href="/">
            Back to overview
          </a>
        </div>
        {chunkError ? null : <p className="route-error__detail">{errorDetail(error)}</p>}
      </section>
    </main>
  );
}
