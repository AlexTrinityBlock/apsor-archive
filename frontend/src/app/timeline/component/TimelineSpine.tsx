import { Fragment, useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type {
  TimelineEventSchema,
  TimelineResponseSchema,
  TimelineSkipSchema,
} from "../../generated-apis-types/schemas";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { formatDateTime, formatNumber } from "../../../lib/format";

import {
  errorText,
  formatDotDay,
  formatRangeCaption,
  toDateInput,
} from "./helpers";

export interface TimelineWindowView {
  readonly key: string;
  readonly label: string;
  readonly rangeLabel: string;
  readonly data: TimelineResponseSchema;
  readonly isCurrent: boolean;
}

interface TimelineSpineProps {
  readonly windows: readonly TimelineWindowView[];
  readonly currentEmptyContent?: ReactNode;
  readonly loadingEarlier: boolean;
  readonly sentinel: ReactNode;
}

export type SentinelState =
  | { readonly kind: "ready"; readonly nextLabel: string }
  | { readonly kind: "loading"; readonly nextLabel: string }
  | { readonly kind: "error"; readonly nextLabel: string; readonly error: unknown }
  | {
      readonly kind: "exhausted";
      readonly title: string;
      readonly detail: string;
      readonly canContinue: boolean;
    };

interface TimelineSentinelProps {
  readonly state: SentinelState;
  readonly onLoadEarlier: () => void;
  readonly onRetry: () => void;
}

const KIND_PILL: Record<TimelineEventSchema["kind"], string> = {
  memory: "MEMORY",
  summary: "SUMMARY",
  file_update: "FILE UPDATE",
};

function countLabel(count: number, singular: string, plural: string): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}

function eventKey(event: TimelineEventSchema): string {
  const source = event.memory_id ?? event.memory_summary_id ?? event.file_id ?? "sample";
  return `${event.kind}-${source}-${event.time}`;
}

function skipKey(fromTime: string, toTime: string): string {
  return `${fromTime}::${toTime}`;
}

function eventSourceLabel(event: TimelineEventSchema): string | null {
  if (event.kind === "memory" && typeof event.memory_id === "number") {
    return `memory:${event.memory_id}`;
  }
  if (event.kind === "summary" && typeof event.memory_summary_id === "number") {
    return `summary:${event.memory_summary_id}`;
  }
  if (event.kind === "file_update" && typeof event.file_id === "number") {
    return `file:${event.file_id}`;
  }
  return null;
}

function EventStatusBadge({ event }: { readonly event: TimelineEventSchema }) {
  if (event.kind === "memory") {
    if (event.status === "deprecated") {
      return <Badge tone="vermilion">Deprecated</Badge>;
    }
    if (event.status === "active") {
      return (
        <Badge tone="moss" dot>
          Active
        </Badge>
      );
    }
    return <Badge tone="neutral">Memory</Badge>;
  }
  if (event.kind === "summary") {
    return <Badge tone="ochre">Summary</Badge>;
  }
  if (event.action === "created") {
    return <Badge tone="moss">Created</Badge>;
  }
  if (event.action === "updated") {
    return <Badge tone="ochre">Updated</Badge>;
  }
  return <Badge tone="neutral">File update</Badge>;
}

function SummaryBody({ content }: { readonly content: string }) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  return (
    <div className="timeline-node__summary">
      <p
        id={contentId}
        className={
          expanded
            ? "timeline-node__content timeline-node__content--summary is-expanded"
            : "timeline-node__content timeline-node__content--summary"
        }
      >
        {content}
      </p>
      <button
        type="button"
        className="timeline-node__expand"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Collapse summary" : "Expand summary"}
        <Icon name={expanded ? "chevron-down" : "chevron-right"} size={13} />
      </button>
    </div>
  );
}

function EventFooter({ event }: { readonly event: TimelineEventSchema }) {
  const sourceLabel = eventSourceLabel(event);
  return (
    <footer className="timeline-node__foot">
      <time className="timeline-node__time" dateTime={event.time}>
        <Icon name="clock" size={11} />
        {formatDateTime(event.time)}
      </time>
      {sourceLabel ? <span className="timeline-node__id">{sourceLabel}</span> : null}
      {event.kind === "memory" && typeof event.memory_id === "number" ? (
        <Link className="timeline-node__link" to={`/memory/${event.memory_id}`}>
          Read memory crystal
          <Icon name="arrow-up-right" size={12} />
        </Link>
      ) : null}
      {event.kind === "file_update" && typeof event.file_id === "number" ? (
        <Link
          className="timeline-node__link"
          to={`/library?tab=files&file=${event.file_id}`}
        >
          Open in library
          <Icon name="arrow-up-right" size={12} />
        </Link>
      ) : null}
    </footer>
  );
}

function EventCard({ event }: { readonly event: TimelineEventSchema }) {
  const isDeprecated = event.kind === "memory" && event.status === "deprecated";
  const className = ["timeline-node", isDeprecated ? "is-deprecated" : null]
    .filter(Boolean)
    .join(" ");

  return (
    <article className={className}>
      <div className="timeline-node__head">
        <div className="timeline-node__head-copy">
          <span className="file-type-pill timeline-node__pill">
            {KIND_PILL[event.kind]} {"\u00b7"} {formatDotDay(event.time)}
          </span>
          {event.kind === "memory" ? (
            <p className="timeline-node__lead">{event.content}</p>
          ) : null}
          {event.kind === "file_update" ? (
            <h3 className="timeline-node__title">{event.content}</h3>
          ) : null}
        </div>
        <EventStatusBadge event={event} />
      </div>

      {event.kind === "summary" ? <SummaryBody content={event.content} /> : null}

      {event.kind === "file_update" && event.raw_file_path ? (
        <code className="timeline-node__path">{event.raw_file_path}</code>
      ) : null}

      <EventFooter event={event} />
    </article>
  );
}

function SkipRow({ skip }: { readonly skip: TimelineSkipSchema }) {
  const total = skip.memory_number + skip.summary_number + skip.file_number;
  const composition = [
    skip.memory_number > 0
      ? countLabel(skip.memory_number, "memory", "memories")
      : null,
    skip.summary_number > 0
      ? countLabel(skip.summary_number, "summary", "summaries")
      : null,
    skip.file_number > 0 ? countLabel(skip.file_number, "file", "files") : null,
  ]
    .filter(Boolean)
    .join(", ");
  return (
    <div
      className="timeline-skip"
      role="note"
      aria-label={`${countLabel(total, "event", "events")} omitted between two samples (${composition}), ${formatDateTime(
        skip.from_time,
      )} to ${formatDateTime(skip.to_time)}`}
    >
      <span className="timeline-skip__rule" aria-hidden="true" />
      <div className="timeline-skip__body">
        <span className="timeline-skip__count">
          <strong>{formatNumber(total)}</strong> {total === 1 ? "event" : "events"} omitted
        </span>
        {skip.memory_number > 0 ? (
          <span className="timeline-skip__kind timeline-skip__kind--memory">
            {countLabel(skip.memory_number, "memory", "memories")}
          </span>
        ) : null}
        {skip.summary_number > 0 ? (
          <span className="timeline-skip__kind timeline-skip__kind--summary">
            {countLabel(skip.summary_number, "summary", "summaries")}
          </span>
        ) : null}
        {skip.file_number > 0 ? (
          <span className="timeline-skip__kind timeline-skip__kind--file">
            {countLabel(skip.file_number, "file", "files")}
          </span>
        ) : null}
        <span className="timeline-skip__range">
          {formatDateTime(skip.from_time)} {"\u2192"} {formatDateTime(skip.to_time)}
        </span>
      </div>
      <span className="timeline-skip__rule" aria-hidden="true" />
    </div>
  );
}

function WindowBody({ data }: { readonly data: TimelineResponseSchema }) {
  const ordered = [...data.events].sort(
    (left, right) => Date.parse(right.time) - Date.parse(left.time),
  );
  const skipByGap = new Map<string, TimelineSkipSchema>();
  for (const skip of data.skips) {
    skipByGap.set(skipKey(skip.from_time, skip.to_time), skip);
  }

  if (ordered.length === 0) {
    return (
      <p className="timeline-window-empty">
        {data.total === 0
          ? "No events were returned for this window."
          : `${formatNumber(data.total)} events were counted in this window but none were sampled.`}
      </p>
    );
  }

  return (
    <>
      {ordered.map((event, index) => {
        const newer = index > 0 ? ordered[index - 1] : null;
        const skip = newer ? skipByGap.get(skipKey(event.time, newer.time)) : undefined;
        return (
          <Fragment key={eventKey(event)}>
            {skip ? <SkipRow skip={skip} /> : null}
            <EventCard event={event} />
          </Fragment>
        );
      })}
    </>
  );
}

function WindowBreak({ window }: { readonly window: TimelineWindowView }) {
  return (
    <div
      className="timeline-window-break"
      role="separator"
      aria-label={`${window.label}: ${window.rangeLabel}`}
    >
      <span className="timeline-window-break__rule" aria-hidden="true" />
      <span className="timeline-window-break__label">{window.label}</span>
      <span className="timeline-window-break__range">{window.rangeLabel}</span>
      <span className="timeline-window-break__count">
        {countLabel(window.data.total, "event", "events")}
      </span>
      <span className="timeline-window-break__rule" aria-hidden="true" />
    </div>
  );
}

/** The load-earlier control at the bottom of the continuous spine. */
export function TimelineSentinel({ state, onLoadEarlier, onRetry }: TimelineSentinelProps) {
  if (state.kind === "loading") {
    return (
      <div className="timeline-sentinel timeline-sentinel--loading" role="status">
        <span className="timeline-sentinel__spinner" aria-hidden="true" />
        <span>Reading earlier window {"\u00b7"} {state.nextLabel}…</span>
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="timeline-sentinel timeline-sentinel--error" role="alert">
        <div className="timeline-sentinel__panel">
          <p className="timeline-sentinel__title">The earlier window did not answer.</p>
          <p className="timeline-sentinel__detail">
            {state.nextLabel} {"\u00b7"} {errorText(state.error)}
          </p>
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <Icon name="history" size={13} />
            Retry earlier window
          </Button>
        </div>
      </div>
    );
  }

  if (state.kind === "exhausted") {
    return (
      <div className="timeline-sentinel timeline-sentinel--exhausted" role="note">
        <div className="timeline-sentinel__panel">
          <p className="timeline-sentinel__title">{state.title}</p>
          <p className="timeline-sentinel__detail">{state.detail}</p>
          {state.canContinue ? (
            <Button variant="ghost" size="sm" onClick={onLoadEarlier}>
              Search further back
              <Icon name="arrow-down" size={13} />
            </Button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="timeline-sentinel">
      <button
        type="button"
        className="timeline-sentinel__button"
        onClick={onLoadEarlier}
        title={`Load the window ${state.nextLabel}`}
      >
        <span className="timeline-sentinel__dot" aria-hidden="true" />
        Load earlier {"\u00b7"} {state.nextLabel}
        <Icon name="arrow-down" size={13} />
      </button>
    </div>
  );
}

/** The continuous 0.7px spine: current window, earlier windows, and the sentinel. */
export function TimelineSpine({
  windows,
  currentEmptyContent,
  loadingEarlier,
  sentinel,
}: TimelineSpineProps) {
  return (
    <section
      className="timeline-spine"
      aria-label="Sampled timeline events"
      aria-busy={loadingEarlier}
    >
      {currentEmptyContent ? (
        <div className="timeline-spine__empty">{currentEmptyContent}</div>
      ) : null}

      {windows.map((window) => (
        <Fragment key={window.key}>
          {window.isCurrent ? null : <WindowBreak window={window} />}
          <WindowBody data={window.data} />
        </Fragment>
      ))}

      {loadingEarlier ? (
        <div className="timeline-skeleton__card timeline-skeleton__card--inline" aria-hidden="true">
          <span className="timeline-skeleton__line timeline-skeleton__line--short" />
          <span className="timeline-skeleton__line" />
          <span className="timeline-skeleton__line timeline-skeleton__line--mid" />
        </div>
      ) : null}

      {sentinel}
    </section>
  );
}

/** Builds the view model for one loaded window; shared by the page and sentinel. */
export function buildWindowView(input: {
  readonly key: string;
  readonly data: TimelineResponseSchema;
  readonly isCurrent: boolean;
}): TimelineWindowView {
  const start = input.data.range_start.slice(0, 10);
  const end = input.data.range_end.slice(0, 10);
  return {
    key: input.key,
    label: input.isCurrent ? "Current window" : "Earlier window",
    rangeLabel: formatRangeCaption(start, end),
    data: input.data,
    isCurrent: input.isCurrent,
  };
}

/** A short date label for the upcoming earlier window. */
export function earlierWindowLabel(anchor: Date, range: number, index: number): string {
  const windowEnd = new Date(anchor);
  windowEnd.setDate(windowEnd.getDate() - range * (index + 1));
  const windowStart = new Date(windowEnd);
  windowStart.setDate(windowStart.getDate() - (range - 1));
  return formatRangeCaption(toDateInput(windowStart), toDateInput(windowEnd));
}
