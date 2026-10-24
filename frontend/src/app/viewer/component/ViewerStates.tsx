import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { viewerErrorMessage } from "./viewer-utils";

interface LoadingProps {
  readonly label?: string;
}

/** A quiet archive placeholder while a renderer or chunk loads. */
export function ViewerLoading({ label = "Opening the file" }: LoadingProps) {
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
      <p className="eyebrow">Preview interrupted</p>
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
