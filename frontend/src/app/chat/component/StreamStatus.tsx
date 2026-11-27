import { Icon } from "../../component/Icon";
import { useI18n, type TranslationKey } from "../../i18n";

/** A dismissible banner for a failure that has no retry surface. */
export function StreamErrorBanner({
  detail,
  onDismiss,
}: {
  readonly detail: string | null;
  readonly onDismiss: () => void;
}) {
  const { t } = useI18n();
  if (detail === null) {
    return null;
  }
  return (
    <div className="chat-stream-error" role="alert">
      <Icon name="info" size={16} />
      <div>
        <strong>{t("chat.page.failureTitle")}</strong>
        <p>{detail}</p>
      </div>
      <button
        type="button"
        className="chat-stream-error__close"
        onClick={onDismiss}
        aria-label={t("chat.page.dismissError")}
      >
        <Icon name="close" size={14} />
      </button>
    </div>
  );
}

/**
 * One visually hidden polite live region for run-state changes (responding,
 * waiting, complete, stopped, failed). Tokens are never announced.
 */
export function StreamLiveRegion({
  message,
}: {
  readonly message: TranslationKey | null;
}) {
  const { t } = useI18n();
  return (
    <p className="visually-hidden" aria-live="polite" aria-atomic="true">
      {message === null ? null : t(message)}
    </p>
  );
}
