import type { ReactNode } from "react";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { ViewerShell } from "./ViewerShell";
import { viewerErrorMessage } from "./viewer-utils";

interface LoadingProps {
  readonly label?: string;
}

/** A quiet archive placeholder while a viewer chunk or document loads. */
export function ViewerLoading({ label = "Opening the leaf" }: LoadingProps) {
  return (
    <div className="viewer-state viewer-state--loading" role="status" aria-live="polite">
      <span className="viewer-loader" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <p className="viewer-state__label">{label}</p>
    </div>
  );
}

/** Route-level fallback used while a lazy viewer module is fetched. */
export function ViewerRouteFallback() {
  return (
    <ViewerShell
      kind="Viewer"
      title="Opening the archive leaf"
      backTo="/"
      backLabel="Archive"
    >
      <ViewerLoading label="Preparing the reading room" />
    </ViewerShell>
  );
}

interface MissingProps {
  readonly title: string;
  readonly message: ReactNode;
  readonly backTo: string;
  readonly backLabel: string;
}

/** A resource was deleted, never existed, or the route id was invalid. */
export function ViewerMissing({ title, message, backTo, backLabel }: MissingProps) {
  return (
    <section className="viewer-state viewer-state--missing reveal reveal-2">
      <p className="eyebrow">Leaf not found</p>
      <h2>{title}</h2>
      <p>{message}</p>
      <ButtonLink to={backTo} variant="secondary" size="sm">
        <Icon name="arrow-right" size={15} className="viewer-back-icon" />
        {backLabel}
      </ButtonLink>
    </section>
  );
}

interface ErrorProps {
  readonly error: unknown;
  readonly title: string;
  readonly onRetry?: () => void;
  readonly downloadUrl?: string;
  readonly downloadName?: string;
}

/** A failed fetch with the server's stable error detail and a retry. */
export function ViewerErrorState({
  error,
  title,
  onRetry,
  downloadUrl,
  downloadName,
}: ErrorProps) {
  return (
    <section className="viewer-state viewer-state--error" role="alert">
      <span className="viewer-state__mark" aria-hidden="true">
        <Icon name="info" size={22} />
      </span>
      <p className="eyebrow">Viewer interrupted</p>
      <h2>{title}</h2>
      <p>{viewerErrorMessage(error)}</p>
      <div className="viewer-state__actions">
        {onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <Icon name="history" size={15} />
            Try again
          </Button>
        ) : null}
        {downloadUrl ? (
          <a
            className="btn btn--ghost btn--sm"
            href={downloadUrl}
            download={downloadName}
          >
            <Icon name="arrow-down" size={15} />
            Download original
          </a>
        ) : null}
      </div>
    </section>
  );
}
