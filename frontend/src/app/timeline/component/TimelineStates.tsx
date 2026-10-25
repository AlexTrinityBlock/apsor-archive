import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

import { errorText } from "./helpers";

interface TimelineSkeletonProps {
  readonly label?: string;
}

/** Initial loading skeleton for the density strip and the sampled spine. */
export function TimelineSkeleton({ label }: TimelineSkeletonProps) {
  const { t } = useI18n();
  const resolvedLabel = label ?? t("insights.timeline.states.skeleton");
  return (
    <div className="timeline-skeleton" role="status" aria-live="polite">
      <div className="timeline-skeleton__strip" aria-hidden="true">
        <span className="timeline-skeleton__line timeline-skeleton__line--short" />
        <span className="timeline-skeleton__line" />
        <span className="timeline-skeleton__line timeline-skeleton__line--mid" />
      </div>
      <div className="timeline-skeleton__spine" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <div className="timeline-skeleton__card" key={index}>
            <span className="timeline-skeleton__line timeline-skeleton__line--short" />
            <span className="timeline-skeleton__line" />
            <span className="timeline-skeleton__line timeline-skeleton__line--mid" />
          </div>
        ))}
      </div>
      <span className="visually-hidden">{resolvedLabel}</span>
    </div>
  );
}

interface TimelineErrorStateProps {
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly isRetrying: boolean;
}

/** A read failure with an explicit retry control. */
export function TimelineErrorState({ error, onRetry, isRetrying }: TimelineErrorStateProps) {
  const { t } = useI18n();
  return (
    <section className="timeline-state timeline-state--error" role="alert">
      <div className="timeline-state__icon" aria-hidden="true">
        <Icon name="info" size={20} />
      </div>
      <div className="timeline-state__copy">
        <p className="eyebrow">{t("insights.timeline.states.errorEyebrow")}</p>
        <h2 className="timeline-state__title">
          {t("insights.timeline.states.errorTitle")}
        </h2>
        <p className="timeline-state__detail">{errorText(error, t)}</p>
        <Button variant="ink" size="sm" onClick={onRetry} disabled={isRetrying}>
          <Icon name="history" size={13} />
          {isRetrying
            ? t("insights.timeline.states.readingWindow")
            : t("insights.timeline.states.retryWindow")}
        </Button>
      </div>
    </section>
  );
}
