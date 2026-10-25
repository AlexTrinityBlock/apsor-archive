import { useEffect } from "react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { useI18n, type Translate } from "../i18n";
import { Button } from "./Button";
import { TreeMark } from "./TreeMark";
import { TreeRings } from "./TreeRings";
import "./route-error.css";

const RELOAD_GUARD_KEY = "apsor-archive.route-error.reload-at";
const CHUNK_ERROR_PATTERN =
  /failed to fetch dynamically imported module|importing a module script failed|chunkloaderror|loading chunk/i;

/** True when a lazy route chunk vanished after a new deployment. */
function isChunkError(error: unknown): boolean {
  if (error instanceof Error) {
    return CHUNK_ERROR_PATTERN.test(error.message);
  }
  return typeof error === "string" && CHUNK_ERROR_PATTERN.test(error);
}

function errorDetail(error: unknown, t: Translate): string {
  if (isRouteErrorResponse(error)) {
    return `${error.status} ${error.statusText}`.trim();
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return t("core.route.unknownError");
}

/**
 * Root route error boundary. A stale lazy chunk reloads once so the browser
 * picks up the new index.html; persistent or unrelated errors get a real page
 * instead of React Router's default "Unexpected Application Error" screen.
 */
export function RouteError() {
  const { t } = useI18n();
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
        <p className="eyebrow">{t("core.route.errorEyebrow")}</p>
        <h1>
          {chunkError
            ? t("core.route.chunkTitle")
            : t("core.route.errorTitle")}
        </h1>
        <p className="route-error__description">
          {chunkError
            ? t("core.route.chunkDescription")
            : t("core.route.errorDescription")}
        </p>
        <div className="route-error__actions">
          <Button variant="primary" onClick={() => window.location.reload()}>
            {t("core.route.reload")}
          </Button>
          <a className="btn btn--secondary btn--md" href="/">
            {t("core.route.backToOverview")}
          </a>
        </div>
        {chunkError ? null : (
          <p className="route-error__detail">{errorDetail(error, t)}</p>
        )}
      </section>
    </main>
  );
}
