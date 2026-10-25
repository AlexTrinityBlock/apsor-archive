import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { viewerErrorMessage } from "./viewer-utils";

interface LoadingProps {
  readonly label?: string;
}

/** A quiet archive placeholder while a renderer or chunk loads. */
export function ViewerLoading({ label }: LoadingProps) {
  const { t } = useI18n();
  return (
    <div className="viewer-state viewer-state--loading" role="status" aria-live="polite">
      <span className="viewer-loader" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <p className="viewer-state__label">{label ?? t("library.viewer.loadingDefault")}</p>
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
  const { t } = useI18n();
  return (
    <section className="viewer-state viewer-state--error" role="alert">
      <span className="viewer-state__mark" aria-hidden="true">
        <Icon name="info" size={22} />
      </span>
      <p className="eyebrow">{t("library.viewer.errorsEyebrow")}</p>
      <h2>{title}</h2>
      <p>{viewerErrorMessage(error, t)}</p>
      <div className="viewer-state__actions">
        {onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <Icon name="history" size={15} />
            {t("library.viewer.retry")}
          </Button>
        ) : null}
        {downloadUrl ? (
          <a
            className="btn btn--ghost btn--sm"
            href={downloadUrl}
            download={downloadName}
          >
            <Icon name="arrow-down" size={15} />
            {t("library.viewer.downloadOriginal")}
          </a>
        ) : null}
      </div>
    </section>
  );
}
