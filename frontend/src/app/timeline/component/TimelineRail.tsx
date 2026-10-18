import { useState } from "react";
import { Link } from "react-router-dom";

import type {
  TimelineEventSchema,
  TimelineSkipSchema,
} from "../../generated-apis-types/schemas";
import type { BadgeTone } from "../../type/ui";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon, type IconName } from "../../component/Icon";
import { formatDateTime, formatNumber } from "../../../lib/format";

interface TimelineRailProps {
  readonly events: TimelineEventSchema[];
  readonly skips: TimelineSkipSchema[];
}

const KIND_META: Record<
  TimelineEventSchema["kind"],
  { readonly label: string; readonly tone: BadgeTone; readonly icon: IconName }
> = {
  memory: { label: "Memory", tone: "vermilion", icon: "memory" },
  summary: { label: "Summary", tone: "ochre", icon: "quote" },
  file_update: { label: "File", tone: "moss", icon: "file" },
};

function gapKey(fromTime: string, toTime: string): string {
  return `${Date.parse(fromTime)}::${Date.parse(toTime)}`;
}

function eventKey(event: TimelineEventSchema): string {
  const sourceId = event.memory_id ?? event.memory_summary_id ?? event.file_id ?? "x";
  return `${event.kind}-${sourceId}-${event.time}`;
}

function countLabel(count: number, singular: string, plural: string): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}

function SkipDivider({ skip }: { readonly skip: TimelineSkipSchema }) {
  const total = skip.memory_number + skip.summary_number + skip.file_number;
  return (
    <div className="timeline-skip" role="note" aria-label={`${total} events omitted between samples`}>
      <span className="timeline-skip__rule" aria-hidden="true" />
      <div className="timeline-skip__body">
        <p className="timeline-skip__count">
          <strong>{formatNumber(total)}</strong> {total === 1 ? "event" : "events"} omitted
        </p>
        <div className="timeline-skip__badges">
          {skip.memory_number > 0 ? (
            <Badge tone="vermilion">
              {countLabel(skip.memory_number, "memory", "memories")}
            </Badge>
          ) : null}
          {skip.summary_number > 0 ? (
            <Badge tone="ochre">
              {countLabel(skip.summary_number, "summary", "summaries")}
            </Badge>
          ) : null}
          {skip.file_number > 0 ? (
            <Badge tone="moss">{countLabel(skip.file_number, "file", "files")}</Badge>
          ) : null}
        </div>
        <span className="timeline-skip__range">
          {formatDateTime(skip.from_time)} {"\u2192"} {formatDateTime(skip.to_time)}
        </span>
      </div>
      <span className="timeline-skip__rule" aria-hidden="true" />
    </div>
  );
}

function SummaryBody({ event }: { readonly event: TimelineEventSchema }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="timeline-event__summary">
      <p
        className={[
          "timeline-event__content",
          "timeline-event__content--summary",
          expanded ? "is-expanded" : null,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {event.content}
      </p>
      <Button
        variant="ghost"
        size="sm"
        className="timeline-event__expand"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Collapse summary" : "Expand summary"}
        <Icon name={expanded ? "chevron-down" : "chevron-right"} size={14} />
      </Button>
    </div>
  );
}

function EventFooter({ event }: { readonly event: TimelineEventSchema }) {
  const meta = KIND_META[event.kind];
  return (
    <footer className="timeline-event__footer">
      <span className="timeline-event__anchor" title={`Selected for sampling anchor ${event.anchor.toFixed(2)}`}>
        <Icon name="ring" size={12} />
        anchor {event.anchor.toFixed(2)}
      </span>
      {event.kind === "file_update" && event.raw_file_path ? (
        <code className="timeline-event__path">{event.raw_file_path}</code>
      ) : null}
      {event.kind === "summary" && event.memory_summary_id ? (
        <span className="timeline-event__id">summary:{event.memory_summary_id}</span>
      ) : null}
      {event.kind === "memory" && event.memory_id ? (
        <Link className="timeline-event__link" to={`/memory/${event.memory_id}`}>
          Read memory {event.memory_id}
          <Icon name="arrow-right" size={14} />
        </Link>
      ) : null}
      {event.kind === "file_update" && event.file_id ? (
        <Link className="timeline-event__link" to={`/library?file=${event.file_id}`}>
          Open file
          <Icon name="arrow-up-right" size={14} />
        </Link>
      ) : null}
      <span className="visually-hidden">{meta.label} event</span>
    </footer>
  );
}

function EventCard({ event }: { readonly event: TimelineEventSchema }) {
  const meta = KIND_META[event.kind];
  const isDeprecated = event.status === "deprecated";
  return (
    <article
      className={[
        "timeline-event",
        `timeline-event--${event.kind.replace("_", "-")}`,
        isDeprecated ? "is-deprecated" : null,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="timeline-rail__node" aria-hidden="true" />
      <header className="timeline-event__head">
        <div className="timeline-event__badges">
          <Badge tone={meta.tone} dot>
            <Icon name={meta.icon} size={11} />
            {meta.label}
          </Badge>
          {event.kind === "file_update" && event.action ? (
            <Badge tone={event.action === "created" ? "moss" : "ochre"}>{event.action}</Badge>
          ) : null}
          {isDeprecated ? <Badge tone="neutral">Deprecated</Badge> : null}
        </div>
        <time className="timeline-event__time" dateTime={event.time}>
          {formatDateTime(event.time)}
        </time>
      </header>

      {event.kind === "summary" ? (
        <SummaryBody event={event} />
      ) : (
        <p
          className={[
            "timeline-event__content",
            event.kind === "file_update" ? "timeline-event__content--file" : null,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {event.content}
        </p>
      )}

      <EventFooter event={event} />
    </article>
  );
}

/** Chronological event rail with an omitted-events divider in each sampled gap. */
export function TimelineRail({ events, skips }: TimelineRailProps) {
  const ordered = [...events].sort((left, right) => Date.parse(left.time) - Date.parse(right.time));
  const skipByGap = new Map<string, TimelineSkipSchema>();
  for (const skip of skips) {
    skipByGap.set(gapKey(skip.from_time, skip.to_time), skip);
  }

  return (
    <section className="timeline-rail reveal reveal-3" aria-labelledby="timeline-rail-title">
      <header className="timeline-rail__head">
        <div>
          <p className="eyebrow">Chronological samples</p>
          <h2 id="timeline-rail-title">The rings, in order</h2>
        </div>
        <Badge tone="neutral">
          {formatNumber(ordered.length)} {ordered.length === 1 ? "anchor" : "anchors"} shown
        </Badge>
      </header>

      <ol className="timeline-rail__events">
        {ordered.map((event, index) => {
          const previous = index > 0 ? ordered[index - 1] : null;
          const skip = previous
            ? skipByGap.get(gapKey(previous.time, event.time))
            : undefined;
          return (
            <li
              className={`timeline-rail__item timeline-rail__item--${event.kind.replace("_", "-")}`}
              key={eventKey(event)}
            >
              {skip ? <SkipDivider skip={skip} /> : null}
              <EventCard event={event} />
            </li>
          );
        })}
      </ol>
    </section>
  );
}
