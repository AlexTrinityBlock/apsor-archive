import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface TimelineHeaderProps {
  readonly rangeLabel: string;
  readonly isFetching: boolean;
}

/** Timeline masthead with the real API range and the memory-recording entry point. */
export function TimelineHeader({ rangeLabel, isFetching }: TimelineHeaderProps) {
  const { t } = useI18n();
  return (
    <header className="timeline-header">
      <div className="timeline-header__copy">
        <div className="timeline-header__kicker">
          <span className="shell-tag">
            {t("insights.timeline.header.kicker")}
          </span>
          <span className="timeline-header__mono">
            {t("insights.timeline.header.kickerMeta")}
          </span>
        </div>
        <h1 className="page-title">{t("insights.timeline.header.title")}</h1>
        <p className="page-desc timeline-header__subtitle">
          {t("insights.timeline.header.description")}
        </p>
      </div>

      <div className="timeline-header__actions">
        <div className="timeline-range-badge" aria-live="polite">
          <span className="mono-label">
            {isFetching
              ? t("insights.timeline.header.readingWindow")
              : t("insights.timeline.header.windowSpan")}
          </span>
          <strong>{rangeLabel}</strong>
        </div>
        <ButtonLink to="/memory/new" variant="ink" size="md">
          <Icon name="plus" size={13} />
          {t("insights.timeline.header.recordMemory")}
        </ButtonLink>
      </div>
    </header>
  );
}
