import type { ReactNode } from "react";

import { useApiErrorMessage, useI18n } from "../../i18n";
import { Button } from "../../component/Button";
import { Icon, type IconName } from "../../component/Icon";

interface MemorySkeletonProps {
  readonly label?: string;
  readonly count?: number;
}

/** Loading placeholders shaped like the vault cards they replace. */
export function MemorySkeleton({ label, count = 3 }: MemorySkeletonProps) {
  const { t } = useI18n();
  const resolvedLabel = label ?? t("memory.states.readingMemories");

  return (
    <div className="memory-skeleton-list" role="status" aria-live="polite">
      <span className="visually-hidden">{resolvedLabel}</span>
      {Array.from({ length: count }, (_, index) => (
        <div className="memory-skeleton" key={index} aria-hidden="true">
          <div className="memory-skeleton__row">
            <span className="memory-skeleton__bar memory-skeleton__bar--id" />
            <span className="memory-skeleton__bar memory-skeleton__bar--time" />
          </div>
          <span className="memory-skeleton__bar memory-skeleton__bar--title" />
          <span className="memory-skeleton__bar" />
          <span className="memory-skeleton__bar memory-skeleton__bar--short" />
        </div>
      ))}
    </div>
  );
}

interface MemoryErrorStateProps {
  readonly title: string;
  readonly description: string;
  readonly error: unknown;
  readonly onRetry: () => void;
}

/** A readable failure state with a real retry action. */
export function MemoryErrorState({
  title,
  description,
  error,
  onRetry,
}: MemoryErrorStateProps) {
  const { t } = useI18n();
  const apiErrorMessage = useApiErrorMessage();

  return (
    <section className="memory-state memory-state--error" role="alert" aria-label={title}>
      <div className="memory-state__mark" aria-hidden="true">
        <Icon name="info" size={24} />
      </div>
      <p className="eyebrow">{t("memory.states.readInterrupted")}</p>
      <h2>{title}</h2>
      <p>{description}</p>
      <p className="memory-state__detail">
        {apiErrorMessage(error, "memory.states.didNotAnswer")}
      </p>
      <div className="memory-state__actions">
        <Button variant="ink" size="sm" onClick={onRetry}>
          {t("memory.states.retry")}
        </Button>
      </div>
    </section>
  );
}

interface MemoryEmptyStateProps {
  readonly icon?: IconName;
  readonly eyebrow: string;
  readonly title: string;
  readonly description: string;
  readonly action?: ReactNode;
}

/** Calm empty state shared by the vault, filtered results, and the reader. */
export function MemoryEmptyState({
  icon = "memory",
  eyebrow,
  title,
  description,
  action,
}: MemoryEmptyStateProps) {
  return (
    <section className="memory-state" aria-label={title}>
      <div className="memory-state__mark" aria-hidden="true">
        <Icon name={icon} size={24} />
      </div>
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{description}</p>
      {action ? <div className="memory-state__actions">{action}</div> : null}
    </section>
  );
}
