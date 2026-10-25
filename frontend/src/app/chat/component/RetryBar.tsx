import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { RetryState } from "../types";

interface RetryBarProps {
  readonly state: RetryState;
  readonly disabled: boolean;
  readonly onRetry: () => void;
}

/**
 * A compact archive notice for an unfinished run.
 *
 * Retry creates a new run for the same user entry; it never appends a second
 * marginalium. The button is disabled while another stream is in flight.
 */
export function RetryBar({ state, disabled, onRetry }: RetryBarProps) {
  const { t } = useI18n();
  if (!state.retryable) {
    return null;
  }

  return (
    <section
      className="chat-retry"
      role="status"
      aria-live="polite"
      aria-label={t("chat.retry.aria")}
    >
      <span className="chat-retry__mark" aria-hidden="true">
        <Icon name="history" size={16} />
      </span>

      <div className="chat-retry__copy">
        <p className="eyebrow">{t("chat.retry.eyebrow")}</p>
        <strong>{t("chat.retry.title")}</strong>
        <p className="chat-retry__body">{t("chat.retry.body")}</p>
        {state.errorCode || state.errorDetail ? (
          <p className="chat-retry__detail">
            {state.errorCode ? <Badge tone="ochre">{state.errorCode}</Badge> : null}
            {state.errorDetail ? <span>{state.errorDetail}</span> : null}
          </p>
        ) : null}
        <p className="chat-retry__note">{t("chat.retry.note")}</p>
      </div>

      <Button
        variant="secondary"
        size="sm"
        className="chat-retry__action"
        onClick={onRetry}
        disabled={disabled}
        aria-label={t("chat.retry.actionAria")}
      >
        <Icon name="history" size={14} />
        {t("core.common.retry")}
      </Button>
    </section>
  );
}
