import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
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
  if (!state.retryable) {
    return null;
  }

  return (
    <section
      className="chat-retry"
      role="status"
      aria-live="polite"
      aria-label="Retry the last run"
    >
      <span className="chat-retry__mark" aria-hidden="true">
        <Icon name="history" size={16} />
      </span>

      <div className="chat-retry__copy">
        <p className="eyebrow">Unfinished run</p>
        <strong>The last run did not finish.</strong>
        <p className="chat-retry__body">
          Retry starts a new run for the same user entry. No duplicate message
          is added.
        </p>
        {state.errorCode || state.errorDetail ? (
          <p className="chat-retry__detail">
            {state.errorCode ? <Badge tone="ochre">{state.errorCode}</Badge> : null}
            {state.errorDetail ? <span>{state.errorDetail}</span> : null}
          </p>
        ) : null}
        <p className="chat-retry__note">
          If the archive stopped at a context or token budget, a retry may reach
          the same limit again.
        </p>
      </div>

      <Button
        variant="secondary"
        size="sm"
        className="chat-retry__action"
        onClick={onRetry}
        disabled={disabled}
        aria-label="Retry the last run for the same user message"
      >
        <Icon name="history" size={14} />
        Retry
      </Button>
    </section>
  );
}
