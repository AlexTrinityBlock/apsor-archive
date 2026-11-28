import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { isChunkError, reloadForNewBuild } from "../../component/chunk-error";
import { useI18n } from "../../i18n";

interface FallbackProps {
  readonly error: unknown;
  readonly downloadUrl?: string;
  readonly downloadName?: string;
  readonly onRetry: () => void;
}

/**
 * What a reader sees when one renderer fails. A vanished chunk (a tab opened
 * before a deployment) offers a reload into the new build; any other error
 * keeps the rest of the page working and offers a retry and the original.
 */
function ViewerFallback({ error, downloadUrl, downloadName, onRetry }: FallbackProps) {
  const { t } = useI18n();
  const chunk = isChunkError(error);
  return (
    <section className="viewer-state viewer-state--error" role="alert">
      <span className="viewer-state__mark" aria-hidden="true">
        <Icon name="info" size={22} />
      </span>
      <p className="eyebrow">{t("library.viewer.errorsEyebrow")}</p>
      <h2>{chunk ? t("library.viewer.boundary.updatedTitle") : t("library.viewer.boundary.title")}</h2>
      <p>
        {chunk ? t("library.viewer.boundary.updatedBody") : t("library.viewer.boundary.body")}
      </p>
      <div className="viewer-state__actions">
        {chunk ? (
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
            <Icon name="history" size={15} />
            {t("library.viewer.boundary.reload")}
          </Button>
        ) : (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <Icon name="history" size={15} />
            {t("library.viewer.retry")}
          </Button>
        )}
        {downloadUrl ? (
          <a className="btn btn--ghost btn--sm" href={downloadUrl} download={downloadName}>
            <Icon name="arrow-down" size={15} />
            {t("library.viewer.downloadOriginal")}
          </a>
        ) : null}
      </div>
    </section>
  );
}

interface BoundaryProps {
  readonly children: ReactNode;
  readonly downloadUrl?: string;
  readonly downloadName?: string;
  /** Replaces the default fallback, e.g. plain text for Markdown. */
  readonly fallback?: (error: unknown, retry: () => void) => ReactNode;
  /** Changing this key clears a previous error (another file opened). */
  readonly resetKey?: string | number;
}

interface BoundaryState {
  readonly error: unknown;
  readonly resetKey: string | number | undefined;
}

/**
 * Error boundary around one file renderer, so a failing preview never takes
 * the Library modal, the chat dialog, or the route down with it.
 */
export class ViewerBoundary extends Component<BoundaryProps, BoundaryState> {
  override state: BoundaryState = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: unknown): Partial<BoundaryState> {
    return { error: error ?? new Error("render failed") };
  }

  static getDerivedStateFromProps(
    props: BoundaryProps,
    state: BoundaryState,
  ): Partial<BoundaryState> | null {
    if (props.resetKey !== state.resetKey) {
      return { error: null, resetKey: props.resetKey };
    }
    return null;
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    if (isChunkError(error)) {
      // A tab from before a deployment: reload once into the new build.
      reloadForNewBuild();
      return;
    }
    console.error("file preview failed", error, info.componentStack);
  }

  private readonly retry = () => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (error === null) {
      return this.props.children;
    }
    if (this.props.fallback && !isChunkError(error)) {
      return this.props.fallback(error, this.retry);
    }
    return (
      <ViewerFallback
        error={error}
        downloadUrl={this.props.downloadUrl}
        downloadName={this.props.downloadName}
        onRetry={this.retry}
      />
    );
  }
}
