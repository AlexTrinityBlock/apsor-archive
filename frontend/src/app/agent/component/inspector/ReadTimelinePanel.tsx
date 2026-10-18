import { Link } from "react-router-dom";

import { formatDateTime, formatNumber, truncate } from "../../../../lib/format";
import {
  excerptOf,
  numberField,
  recordId,
  recordList,
  textField,
} from "../../trace";
import { LivePanel, PanelEmpty, type PanelProps } from "./common";

interface TimelineEvent {
  readonly kind: string;
  readonly time: string | null;
  readonly content: string;
  readonly memoryId: number | null;
  readonly fileId: number | null;
  readonly position: number;
}

function timeValue(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

function eventPosition(
  time: string | null,
  start: number | null,
  end: number | null,
): number {
  const value = timeValue(time);
  if (value === null || start === null || end === null || end <= start) {
    return 0.5;
  }
  return Math.min(1, Math.max(0, (value - start) / (end - start)));
}

function eventsOf(data: Record<string, unknown> | null): TimelineEvent[] {
  const start = timeValue(textField(data, "range_start"));
  const end = timeValue(textField(data, "range_end"));
  return recordList(data?.events).map((record) => {
    const time = textField(record, "time");
    return {
      kind: textField(record, "kind") ?? "event",
      time,
      content: excerptOf(record, ["content", "excerpt"], 300),
      memoryId: recordId(record, "memory_id"),
      fileId: recordId(record, "file_id"),
      position: eventPosition(time, start, end),
    };
  });
}

function DensityBars({ events }: { readonly events: readonly TimelineEvent[] }) {
  const buckets = new Array<number>(20).fill(0);
  for (const event of events) {
    const index = Math.min(19, Math.max(0, Math.floor(event.position * 20)));
    buckets[index] += 1;
  }
  const peak = Math.max(1, ...buckets);
  return (
    <div className="pi-ribbon__density" aria-hidden="true">
      {buckets.map((count, index) => (
        <span
          key={index}
          style={{ height: `${Math.max(8, (count / peak) * 100)}%` }}
          data-empty={count === 0 ? "true" : "false"}
        />
      ))}
    </div>
  );
}

function EventCard({ event }: { readonly event: TimelineEvent }) {
  return (
    <li className="pi-ribbon__event">
      <span className="pi-ribbon__event-dot" aria-hidden="true" />
      <div className="pi-ribbon__event-body">
        <header>
          <span className="pi-ribbon__event-kind">{event.kind}</span>
          {event.time ? (
            <time dateTime={event.time}>{formatDateTime(event.time)}</time>
          ) : null}
        </header>
        {event.content.length > 0 ? (
          <p>{truncate(event.content, 300)}</p>
        ) : (
          <p className="is-muted">No inline event text was recorded.</p>
        )}
        <div className="pi-ribbon__event-links">
          {event.memoryId !== null ? (
            <Link to={`/viewer/memory/${event.memoryId}`}>memory:{event.memoryId}</Link>
          ) : null}
          {event.fileId !== null ? (
            <Link to={`/viewer/file/${event.fileId}`}>file:{event.fileId}</Link>
          ) : null}
        </div>
      </div>
    </li>
  );
}

/** `read_timeline`: a temporal ribbon, density strip, and event cards. */
export function ReadTimelinePanel({ item }: PanelProps) {
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Sampling the requested date window." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="timeline"
        title="The timeline window could not be read"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  const data = item.data;
  const events = eventsOf(data);
  const total = numberField(data, "total");
  const sampled = numberField(data, "sampled");

  return (
    <div className="pi-ribbon">
      <header className="pi-ribbon__head">
        <div>
          <p className="eyebrow">Temporal ribbon</p>
          <strong>
            {textField(data, "range_start") ?? "Unbounded"} →{" "}
            {textField(data, "range_end") ?? "now"}
          </strong>
        </div>
        <p className="pi-ribbon__stats">
          {formatNumber(events.length)} shown
          {total !== null ? ` · ${formatNumber(total)} events` : ""}
          {sampled !== null && sampled !== total ? ` · ${formatNumber(sampled)} sampled` : ""}
        </p>
      </header>

      <div className="pi-ribbon__track" aria-hidden="true">
        <DensityBars events={events} />
        <div className="pi-ribbon__line">
          {events.map((event, index) => (
            <span
              className="pi-ribbon__pin"
              key={`${event.time ?? "event"}-${index}`}
              style={{ left: `${event.position * 100}%` }}
              data-kind={event.kind}
              title={`${event.kind} · ${event.time ?? "undated"}`}
            />
          ))}
        </div>
      </div>

      {events.length === 0 ? (
        <PanelEmpty
          icon="timeline"
          title="No events in this range"
          detail="The range was sampled, but no memory, summary, or file event fell inside it."
        />
      ) : (
        <ol className="pi-ribbon__events">
          {events.map((event, index) => (
            <EventCard event={event} key={`${event.time ?? "event"}-${index}`} />
          ))}
        </ol>
      )}
    </div>
  );
}
