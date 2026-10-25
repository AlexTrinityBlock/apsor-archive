import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  useGetHealth,
  useGetStats,
  useReadPath,
  useReadTimeline,
} from "../generated-apis-types";
import type {
  HealthSchema,
  PathFileSchema,
  ReadTimelineParams,
  StatsSchema,
  TimelineEventSchema,
} from "../generated-apis-types/schemas";
import { Badge } from "../component/Badge";
import { Button, ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { Panel } from "../component/Panel";
import { StatCard } from "../component/StatCard";
import {
  localizeStatus,
  translateApiError,
  useI18n,
  type Translate,
  type TranslationKey,
} from "../i18n";
import type { BadgeTone } from "../type/ui";
import {
  basename,
  formatBytes,
  truncate,
} from "../../lib/format";
import "./home.css";


const TIMELINE_WINDOW_DAYS = 30;
const RECENT_FILE_LIMIT = 4;
const RECENT_EVENT_LIMIT = 4;

const TIMELINE_KIND_TONES: Record<TimelineEventSchema["kind"], BadgeTone> = {
  memory: "moss",
  summary: "ochre",
  file_update: "neutral",
};

interface StatCardData {
  readonly label: string;
  readonly value: string;
  readonly note: string;
  readonly accent: "moss" | "ink" | "ochre" | "vermilion";
}

interface RecentFile {
  readonly key: string;
  readonly fileId: number;
  readonly name: string;
  readonly path: string | null;
  readonly sizeBytes: number | null;
  readonly totalChunks: number | null;
  readonly action: string | null;
  readonly time: string;
}


function fileHref(fileId: number): string {
  return `/library?tab=files&file=${fileId}&chunk=1`;
}

function errorText(
  error: unknown,
  t: Translate,
  fallbackKey: TranslationKey,
): string {
  return translateApiError(error, t, fallbackKey);
}

function fileTypeLabel(name: string): string {
  const base = basename(name);
  const dot = base.lastIndexOf(".");
  if (dot < 0 || dot === base.length - 1) {
    return "FILE";
  }
  const extension = base.slice(dot + 1).toLowerCase();
  if (extension === "markdown") {
    return "MD";
  }
  if (extension === "jpeg") {
    return "JPG";
  }
  return extension.slice(0, 4).toUpperCase();
}

function timelineParamsFor(value: string | null | undefined): ReadTimelineParams | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  // The API interprets the anchor in the configured server timezone. Advance one
  // UTC day so the newest memory always falls inside the inclusive window.
  const anchor = new Date(date.getTime());
  anchor.setUTCDate(anchor.getUTCDate() + 1);
  return {
    year: anchor.getUTCFullYear(),
    month: anchor.getUTCMonth() + 1,
    day: anchor.getUTCDate(),
    day_range: TIMELINE_WINDOW_DAYS,
  };
}

function fallbackTimelineParams(): ReadTimelineParams {
  const now = new Date();
  return {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
    day: now.getDate(),
    day_range: TIMELINE_WINDOW_DAYS,
  };
}

function buildStatCards(
  stats: StatsSchema | undefined,
  t: Translate,
  formatNumber: (value: number) => string,
): readonly StatCardData[] {
  const deprecated = stats
    ? Math.max(0, stats.memory_count - stats.active_memory_count)
    : 0;
  return [
    {
      label: t("core.home.statFiles"),
      value: stats
        ? formatNumber(stats.file_count)
        : t("core.common.notAvailable"),
      note: stats
        ? t("core.home.statFilesNote", {
            size: formatBytes(stats.storage_bytes),
          })
        : t("core.home.countsUnavailable"),
      accent: "moss",
    },
    {
      label: t("core.home.statChunks"),
      value: stats
        ? formatNumber(stats.chunk_count)
        : t("core.common.notAvailable"),
      note: stats
        ? t("core.home.statChunksNote")
        : t("core.home.countsUnavailable"),
      accent: "ink",
    },
    {
      label: t("core.home.statMemories"),
      value: stats
        ? formatNumber(stats.memory_count)
        : t("core.common.notAvailable"),
      note: stats
        ? t("core.home.statMemoriesNote", {
            active: formatNumber(stats.active_memory_count),
            deprecated: formatNumber(deprecated),
          })
        : t("core.home.countsUnavailable"),
      accent: "ochre",
    },
    {
      label: t("core.home.statSummaries"),
      value: stats
        ? formatNumber(stats.summary_count)
        : t("core.common.notAvailable"),
      note: stats
        ? t("core.home.statSummariesNote")
        : t("core.home.countsUnavailable"),
      accent: "vermilion",
    },
  ];
}

function dedupeTimelineFiles(
  events: readonly TimelineEventSchema[],
  t: Translate,
): RecentFile[] {
  const byId = new Map<number, RecentFile>();
  for (const event of events) {
    if (event.kind !== "file_update" || event.file_id == null) {
      continue;
    }
    const path = event.raw_file_path?.trim() || null;
    const name =
      event.content.trim() ||
      (path
        ? basename(path)
        : t("core.home.eventFileFallback", { id: event.file_id }));
    const next: RecentFile = {
      key: `timeline-file-${event.file_id}`,
      fileId: event.file_id,
      name,
      path,
      sizeBytes: null,
      totalChunks: null,
      action: event.action ?? null,
      time: event.time,
    };
    const existing = byId.get(event.file_id);
    if (!existing || Date.parse(next.time) > Date.parse(existing.time)) {
      byId.set(event.file_id, next);
    }
  }
  return [...byId.values()]
    .sort((left, right) => Date.parse(right.time) - Date.parse(left.time))
    .slice(0, RECENT_FILE_LIMIT);
}

function recentPathFiles(files: readonly PathFileSchema[]): RecentFile[] {
  return [...files]
    .sort((left, right) => Date.parse(right.update_time) - Date.parse(left.update_time))
    .slice(0, RECENT_FILE_LIMIT)
    .map((file) => ({
      key: `path-file-${file.file_id}`,
      fileId: file.file_id,
      name: file.file_name,
      path: file.raw_file_path,
      sizeBytes: file.size_bytes,
      totalChunks: file.total_chunks,
      action: null,
      time: file.update_time,
    }));
}

function eventKey(event: TimelineEventSchema, index: number): string {
  const source =
    event.memory_id ?? event.memory_summary_id ?? event.file_id ?? event.raw_file_path ?? "event";
  return `${event.kind}-${String(source)}-${event.time}-${index}`;
}

function eventLabel(event: TimelineEventSchema, t: Translate): string {
  if (event.kind === "memory") {
    return event.status === "deprecated"
      ? t("core.home.eventMemorySuperseded")
      : t("core.home.eventMemoryCrystallized");
  }
  if (event.kind === "summary") {
    return t("core.home.eventSummarySynthesized");
  }
  return event.action === "created"
    ? t("core.home.eventFileCreated")
    : t("core.home.eventFileUpdated");
}

function eventTone(event: TimelineEventSchema): BadgeTone {
  if (event.kind === "memory" && event.status === "deprecated") {
    return "vermilion";
  }
  return TIMELINE_KIND_TONES[event.kind];
}

function eventFallbackContent(event: TimelineEventSchema, t: Translate): string {
  if (event.kind === "memory" && event.memory_id != null) {
    return t("core.home.eventMemoryFallback", { id: event.memory_id });
  }
  if (event.kind === "summary" && event.memory_summary_id != null) {
    return t("core.home.eventSummaryFallback", { id: event.memory_summary_id });
  }
  if (event.kind === "file_update") {
    return (
      event.raw_file_path?.trim() ||
      t("core.home.eventFileFallback", {
        id: event.file_id ?? t("core.common.notAvailable"),
      })
    );
  }
  return t("core.home.noExcerpt");
}

function eventLink(
  event: TimelineEventSchema,
  t: Translate,
): { to: string; label: string } | null {
  if (event.kind === "memory" && event.memory_id != null) {
    return { to: `/memory/${event.memory_id}`, label: t("core.home.readMemory") };
  }
  if (event.kind === "file_update" && event.file_id != null) {
    return {
      to: fileHref(event.file_id),
      label: t("core.home.openInLibrary"),
    };
  }
  return null;
}

function StatusChip({
  health,
  pending,
  error,
}: {
  readonly health: HealthSchema | undefined;
  readonly pending: boolean;
  readonly error: boolean;
}) {
  const { t } = useI18n();
  let tone = "loading";
  let label = t("core.home.statusChecking");
  let detail = t("core.home.statusReadingHealth");

  if (error) {
    tone = "error";
    label = t("core.home.statusOffline");
    detail = t("core.home.statusHealthNoAnswer");
  } else if (health) {
    detail = t("core.status.detail", {
      database: localizeStatus(t, health.database),
      cache: localizeStatus(t, health.cache),
      ai: localizeStatus(t, health.ai),
    });
    if (health.database !== "ok") {
      tone = "error";
      label = t("core.home.statusDegradedDatabase", {
        status: localizeStatus(t, health.database),
      });
    } else if (health.status !== "ok") {
      tone = "degraded";
      label = t("core.home.statusDegraded", {
        status: localizeStatus(t, health.status),
      });
    } else if (health.cache !== "ok") {
      tone = "degraded";
      label = t("core.home.statusDegradedCache", {
        status: localizeStatus(t, health.cache),
      });
    } else {
      tone = "ok";
      label = t("core.home.statusLive", { version: health.version });
    }
  }

  return (
    <span
      className={`overview-status overview-status--${tone}`}
      role="status"
      title={detail}
    >
      <span
        className={pending ? "status-dot status-dot--pending" : "status-dot"}
        aria-hidden="true"
      />
      <span>{label}</span>
    </span>
  );
}

function InlineError({
  title,
  detail,
  onRetry,
  retrying,
}: {
  readonly title: string;
  readonly detail: string;
  readonly onRetry: () => void;
  readonly retrying: boolean;
}) {
  const { t } = useI18n();

  return (
    <div className="overview-inline-state overview-inline-state--error" role="alert">
      <span className="overview-inline-state__icon" aria-hidden="true">
        <Icon name="info" size={18} />
      </span>
      <div className="overview-inline-state__copy">
        <p className="overview-inline-state__title">{title}</p>
        <p className="overview-inline-state__detail">{detail}</p>
      </div>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={onRetry}
        disabled={retrying}
      >
        {retrying ? t("core.common.retrying") : t("core.common.retry")}
      </Button>
    </div>
  );
}

function InlineEmpty({
  icon = "file",
  title,
  description,
  action,
}: {
  readonly icon?: "file" | "timeline" | "search";
  readonly title: string;
  readonly description: string;
  readonly action?: ReactNode;
}) {
  return (
    <div className="overview-inline-state overview-inline-state--empty">
      <span className="overview-inline-state__icon" aria-hidden="true">
        <Icon name={icon} size={20} />
      </span>
      <div className="overview-inline-state__copy">
        <p className="overview-inline-state__title">{title}</p>
        <p className="overview-inline-state__detail">{description}</p>
      </div>
      {action ? <div className="overview-inline-state__action">{action}</div> : null}
    </div>
  );
}

function StatSkeleton() {
  const { t } = useI18n();

  return (
    <section aria-label={t("core.home.statsAria")} aria-busy="true">
      <div className="stats-cards-grid">
        {[0, 1, 2, 3].map((index) => (
          <div className="stat-card overview-stat-skeleton" key={index} aria-hidden="true">
            <span className="overview-skeleton overview-skeleton--label" />
            <span className="overview-skeleton overview-skeleton--value" />
            <span className="overview-skeleton overview-skeleton--note" />
          </div>
        ))}
      </div>
    </section>
  );
}

function FileRowsSkeleton() {
  const { t } = useI18n();

  return (
    <div
      className="overview-file-list"
      aria-busy="true"
      aria-label={t("core.home.recentFilesAria")}
    >
      {[0, 1, 2, 3].map((index) => (
        <div className="overview-file overview-file--skeleton" key={index} aria-hidden="true">
          <span className="overview-skeleton overview-skeleton--type" />
          <span className="overview-file__copy">
            <span className="overview-skeleton overview-skeleton--name" />
            <span className="overview-skeleton overview-skeleton--meta" />
          </span>
          <span className="overview-skeleton overview-skeleton--time" />
        </div>
      ))}
    </div>
  );
}

function TimelineSkeleton() {
  const { t } = useI18n();

  return (
    <div
      className="overview-timeline"
      aria-busy="true"
      aria-label={t("core.home.timelineAria")}
    >
      {[0, 1, 2, 3].map((index) => (
        <div className="overview-event" key={index} aria-hidden="true">
          <div className="overview-event__head">
            <span className="overview-skeleton overview-skeleton--badge" />
            <span className="overview-skeleton overview-skeleton--time" />
          </div>
          <span className="overview-skeleton overview-skeleton--line" />
          <span className="overview-skeleton overview-skeleton--line is-short" />
        </div>
      ))}
    </div>
  );
}

function RecentFilesPanel({
  files,
  loading,
  error,
  usingFallback,
  timelineError,
  onRetry,
  retrying,
}: {
  readonly files: readonly RecentFile[];
  readonly loading: boolean;
  readonly error: unknown;
  readonly usingFallback: boolean;
  readonly timelineError: unknown;
  readonly onRetry: () => void;
  readonly retrying: boolean;
}) {
  const { t, formatDateTime, formatNumber, formatRelative } = useI18n();
  let body: ReactNode;
  if (loading) {
    body = <FileRowsSkeleton />;
  } else if (error) {
    body = (
      <InlineError
        title={t("core.home.recentFilesErrorTitle")}
        detail={errorText(
          error,
          t,
          "core.home.recentFilesErrorFallback",
        )}
        onRetry={onRetry}
        retrying={retrying}
      />
    );
  } else if (files.length === 0) {
    body = (
      <InlineEmpty
        title={t("core.home.recentFilesEmptyTitle")}
        description={t("core.home.recentFilesEmptyDescription")}
        action={
          <ButtonLink to="/library" variant="ink" size="sm">
            {t("core.home.uploadFile")}
            <Icon name="arrow-right" size={14} />
          </ButtonLink>
        }
      />
    );
  } else {
    body = (
      <>
        {usingFallback && timelineError ? (
          <div className="overview-fallback-note" role="status">
            <span>{t("core.home.fallbackNote")}</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onRetry}
              disabled={retrying}
            >
              {retrying
                ? t("core.common.retrying")
                : t("core.home.retryTimeline")}
            </Button>
          </div>
        ) : null}
        <div className="overview-file-list">
          {files.map((file) => (
            <Link className="overview-file" to={fileHref(file.fileId)} key={file.key}>
              <span className="file-type-pill">{fileTypeLabel(file.name)}</span>
              <span className="overview-file__copy">
                <span className="overview-file__name" title={file.name}>
                  {file.name}
                </span>
                <span className="overview-file__meta">
                  <span title={file.path ?? undefined}>
                    {file.path ?? t("core.home.pathUnavailable")}
                  </span>
                  {file.totalChunks !== null ? (
                    <span>
                      ·{" "}
                      {t("core.home.fileChunks", {
                        count: formatNumber(file.totalChunks),
                      })}
                    </span>
                  ) : null}
                  {file.action ? <span>· {file.action}</span> : null}
                </span>
              </span>
              <span className="overview-file__right">
                {file.sizeBytes !== null ? <span>{formatBytes(file.sizeBytes)}</span> : null}
                <time dateTime={file.time} title={formatDateTime(file.time)}>
                  {formatRelative(file.time)}
                </time>
              </span>
            </Link>
          ))}
        </div>
      </>
    );
  }

  return (
    <Panel
      className="overview-panel"
      title={
        <span className="overview-panel__title">
          <Icon name="file" size={15} />
          {t("core.home.recentFilesTitle")}
        </span>
      }
      action={
        <Link className="box-view-all" to="/library">
          <span>{t("core.home.viewAllFiles")}</span>
          <Icon name="chevron-right" size={12} />
        </Link>
      }
    >
      {body}
    </Panel>
  );
}

function RecentTimelinePanel({
  events,
  total,
  rangeStart,
  rangeEnd,
  loading,
  error,
  onRetry,
  retrying,
}: {
  readonly events: readonly TimelineEventSchema[];
  readonly total: number | undefined;
  readonly rangeStart: string | undefined;
  readonly rangeEnd: string | undefined;
  readonly loading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly retrying: boolean;
}) {
  const {
    t,
    formatDate,
    formatDateTime,
    formatNumber,
    formatRelative,
  } = useI18n();
  let body: ReactNode;
  if (loading) {
    body = <TimelineSkeleton />;
  } else if (error) {
    body = (
      <InlineError
        title={t("core.home.timelineErrorTitle")}
        detail={errorText(error, t, "core.home.timelineErrorFallback")}
        onRetry={onRetry}
        retrying={retrying}
      />
    );
  } else if (events.length === 0) {
    body = (
      <InlineEmpty
        icon="timeline"
        title={t("core.home.timelineEmptyTitle")}
        description={t("core.home.timelineEmptyDescription")}
        action={
          <ButtonLink to="/timeline" variant="secondary" size="sm">
            {t("core.home.openTimeline")}
            <Icon name="arrow-right" size={14} />
          </ButtonLink>
        }
      />
    );
  } else {
    body = (
      <div className="overview-timeline">
        {events.map((event, index) => {
          const link = eventLink(event, t);
          return (
            <article className="overview-event" key={eventKey(event, index)}>
              <div className="overview-event__head">
                <Badge tone={eventTone(event)} dot>
                  {eventLabel(event, t)}
                </Badge>
                <time
                  className="overview-event__time"
                  dateTime={event.time}
                  title={formatDateTime(event.time)}
                >
                  {formatRelative(event.time)}
                </time>
              </div>
              <p className="overview-event__text">
                {truncate(
                  event.content.trim() || eventFallbackContent(event, t),
                  190,
                )}
              </p>
              {link ? (
                <Link className="overview-event__link" to={link.to}>
                  {link.label}
                  <Icon name="arrow-right" size={12} />
                </Link>
              ) : null}
            </article>
          );
        })}
      </div>
    );
  }

  const rangeLabel =
    rangeStart && rangeEnd
      ? `${formatDate(rangeStart)} – ${formatDate(rangeEnd)}`
      : t("core.home.timelineLastDays", { days: TIMELINE_WINDOW_DAYS });
  const countLabel =
    total === undefined
      ? t("core.home.timelineWindow")
      : t("core.home.timelineCount", {
          shown: formatNumber(events.length),
          total: formatNumber(total),
        });

  return (
    <Panel
      className="overview-panel"
      title={
        <span className="overview-panel__title">
          <Icon name="timeline" size={15} />
          {t("core.home.timelineTitle")}
        </span>
      }
      action={
        <div className="overview-panel__action">
          <span className="overview-panel__meta" title={rangeLabel}>
            {countLabel}
          </span>
          <Link className="box-view-all" to="/timeline">
            <span>{t("core.home.viewTimeline")}</span>
            <Icon name="chevron-right" size={12} />
          </Link>
        </div>
      }
    >
      {body}
    </Panel>
  );
}

/**
 * The archive dashboard: health, live counts, recent files, and the latest
 * timeline events. All data comes from the existing stats, health, timeline,
 * and path-listing endpoints.
 */
export function DashboardPage() {
  const { t, formatNumber } = useI18n();

  const statsQuery = useGetStats({ query: { staleTime: 30_000 } });
  const healthQuery = useGetHealth({
    query: { staleTime: 60_000, refetchInterval: 60_000 },
  });

  const timelineAnchor = statsQuery.data?.newest_memory_time ?? null;
  const timelineParams = useMemo(
    () => timelineParamsFor(timelineAnchor) ?? fallbackTimelineParams(),
    [timelineAnchor],
  );
  const timelineQuery = useReadTimeline(timelineParams, {
    query: { enabled: !statsQuery.isPending, staleTime: 60_000 },
  });

  const timelineFiles = useMemo(
    () => dedupeTimelineFiles(timelineQuery.data?.events ?? [], t),
    [t, timelineQuery.data],
  );
  const needsPathFallback = !timelineQuery.isPending && timelineFiles.length === 0;
  const pathQuery = useReadPath(
    { path: "/", path_depth: 1 },
    { query: { enabled: needsPathFallback, staleTime: 60_000 } },
  );
  const fallbackFiles = useMemo(
    () => recentPathFiles(pathQuery.data?.files ?? []),
    [pathQuery.data],
  );
  const recentFiles = timelineFiles.length > 0 ? timelineFiles : fallbackFiles;
  const usingFallback = timelineFiles.length === 0;

  const timelineEvents = useMemo(
    () =>
      [...(timelineQuery.data?.events ?? [])]
        .sort((left, right) => Date.parse(right.time) - Date.parse(left.time))
        .slice(0, RECENT_EVENT_LIMIT),
    [timelineQuery.data],
  );

  const stats = statsQuery.data;

  const retryStats = () => void statsQuery.refetch();
  const retryTimeline = () => void timelineQuery.refetch();
  const retryFiles = () => {
    void timelineQuery.refetch();
    if (needsPathFallback) {
      void pathQuery.refetch();
    }
  };

  const filesLoading =
    timelineQuery.isPending || (needsPathFallback && pathQuery.isPending);
  const retryingFiles = timelineQuery.isFetching || pathQuery.isFetching;

  let fileError: unknown = null;
  if (!filesLoading && recentFiles.length === 0) {
    if (needsPathFallback && pathQuery.isError) {
      fileError = pathQuery.error;
    } else if (timelineQuery.isError) {
      fileError = timelineQuery.error;
    }
  }

  return (
    <div className="content-container overview-page">
      <header className="overview-masthead">
        <div className="overview-masthead__top">
          <div className="overview-title-group">
            <p className="eyebrow eyebrow--plain">{t("core.home.eyebrow")}</p>
            <h1 className="overview-title">{t("core.home.title")}</h1>
          </div>
          <div className="overview-masthead__actions">
            <StatusChip
              health={healthQuery.data}
              pending={healthQuery.isPending}
              error={healthQuery.isError}
            />
            <ButtonLink to="/search" variant="secondary" size="sm">
              <Icon name="search" size={14} />
              {t("core.home.search")}
            </ButtonLink>
          </div>
        </div>
      </header>

      {statsQuery.isPending ? (
        <StatSkeleton />
      ) : (
        <section aria-labelledby="overview-stats-title">
          <h2 className="visually-hidden" id="overview-stats-title">
            {t("core.home.statsAria")}
          </h2>
          {statsQuery.isError ? (
            <div className="overview-stats-error">
              <InlineError
                title={t("core.home.statsErrorTitle")}
                detail={errorText(
                  statsQuery.error,
                  t,
                  "core.home.statsErrorFallback",
                )}
                onRetry={retryStats}
                retrying={statsQuery.isFetching}
              />
            </div>
          ) : null}
          <div className="stats-cards-grid">
            {buildStatCards(stats, t, formatNumber).map((stat, index) => (
              <StatCard
                key={stat.label}
                label={stat.label}
                value={stat.value}
                note={stat.note}
                accent={stat.accent}
                index={String(index + 1).padStart(2, "0")}
              />
            ))}
          </div>
        </section>
      )}

      <div className="overview-split">
        <RecentFilesPanel
          files={recentFiles}
          loading={filesLoading}
          error={fileError}
          usingFallback={usingFallback}
          timelineError={timelineQuery.error}
          onRetry={retryFiles}
          retrying={retryingFiles}
        />
        <RecentTimelinePanel
          events={timelineEvents}
          total={timelineQuery.data?.total}
          rangeStart={timelineQuery.data?.range_start}
          rangeEnd={timelineQuery.data?.range_end}
          loading={timelineQuery.isPending}
          error={timelineQuery.error}
          onRetry={retryTimeline}
          retrying={timelineQuery.isFetching}
        />
      </div>

    </div>
  );
}
