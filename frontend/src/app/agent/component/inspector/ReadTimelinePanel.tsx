import { Link } from "react-router-dom";

import { useI18n } from "../../../i18n";
import { truncate } from "../../../../lib/format";
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
      kind: textField(record, "kind") ?? "",
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
  const { t, formatDateTime } = useI18n();
  return (
    <li className="pi-ribbon__event">
      <span className="pi-ribbon__event-dot" aria-hidden="true" />
      <div className="pi-ribbon__event-body">
        <header>
          <span className="pi-ribbon__event-kind">
            {event.kind || t("chat.panels.timeline.eventFallback")}
          </span>
          {event.time ? (
            <time dateTime={event.time}>{formatDateTime(event.time)}</time>
          ) : null}
        </header>
        {event.content.length > 0 ? (
          <p>{truncate(event.content, 300)}</p>
        ) : (
          <p className="is-muted">{t("chat.panels.timeline.noText")}</p>
        )}
        <div className="pi-ribbon__event-links">
          {event.memoryId !== null ? (
            <Link to={`/memory/${event.memoryId}`}>memory:{event.memoryId}</Link>
          ) : null}
          {event.fileId !== null ? (
            <Link to={`/library?tab=files&file=${event.fileId}`}>file:{event.fileId}</Link>
          ) : null}
        </div>
      </div>
    </li>
  );
}

/** `read_timeline`: a temporal ribbon, density strip, and event cards. */
export function ReadTimelinePanel({ item }: PanelProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return (
      <LivePanel item={item} detail={t("chat.panels.timeline.liveDetail")} />
    );
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="timeline"
        title={t("chat.panels.timeline.errorTitle")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
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
          <p className="eyebrow">{t("chat.panels.timeline.heading")}</p>
          <strong>
            {textField(data, "range_start")
              ? formatDateTime(textField(data, "range_start") ?? "")
              : t("chat.panels.timeline.unbounded")}{" "}
            →{" "}
            {textField(data, "range_end")
              ? formatDateTime(textField(data, "range_end") ?? "")
              : t("chat.panels.timeline.now")}
          </strong>
        </div>
        <p className="pi-ribbon__stats">
          {t("chat.panels.timeline.shown", {
            count: formatNumber(events.length),
          })}
          {total !== null
            ? ` · ${t("chat.panels.timeline.events", {
                count: formatNumber(total),
              })}`
            : ""}
          {sampled !== null && sampled !== total
            ? ` · ${t("chat.panels.timeline.sampled", {
                count: formatNumber(sampled),
              })}`
            : ""}
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
              title={`${
                event.kind || t("chat.panels.timeline.eventFallback")
              } · ${
                event.time
                  ? formatDateTime(event.time)
                  : t("chat.panels.timeline.undated")
              }`}
            />
          ))}
        </div>
      </div>

      {events.length === 0 ? (
        <PanelEmpty
          icon="timeline"
          title={t("chat.panels.timeline.emptyTitle")}
          detail={t("chat.panels.timeline.emptyDetail")}
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
