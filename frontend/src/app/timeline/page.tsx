import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { QueryState } from "../component/QueryState";
import { useListMemories } from "../generated-apis-types/memories/memories";
import { useReadTimeline } from "../generated-apis-types/timeline/timeline";

import { MemoryComposer } from "./component/MemoryComposer";
import { SummaryPanel } from "./component/SummaryPanel";
import { TimelineControls } from "./component/TimelineControls";
import { TimelineDensity } from "./component/TimelineDensity";
import { TimelineRail } from "./component/TimelineRail";
import {
  addDays,
  formatRangeCaption,
  parseDateParams,
  readHistoryParam,
  readRangeParam,
  writeDateParams,
} from "./component/helpers";
import "./timeline.css";

const DEMO_SEASON_ANCHOR = new Date(2026, 8, 30);
const DEMO_SEASON_RANGE = 30;

/** Sparse timeline: URL-driven window, density strip, rail, summary, composer. */
export function TimelinePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const defaultsApplied = useRef(false);
  const navigated = useRef(false);

  const latestMemories = useListMemories({ limit: 1 });
  const newestMemory = latestMemories.data?.resources[0] ?? null;
  const newestTime = newestMemory ? new Date(newestMemory.update_time) : null;
  const newestDate = newestTime && !Number.isNaN(newestTime.getTime()) ? newestTime : null;

  const urlDate = parseDateParams(searchParams);
  const anchor = urlDate ?? newestDate ?? new Date();
  const range = readRangeParam(searchParams);
  const includeHistory = readHistoryParam(searchParams);
  const caption = formatRangeCaption(anchor, range);

  useEffect(() => {
    if (defaultsApplied.current) {
      return;
    }
    if (parseDateParams(searchParams)) {
      defaultsApplied.current = true;
      return;
    }
    if (latestMemories.isPending) {
      return;
    }
    if (navigated.current) {
      defaultsApplied.current = true;
      return;
    }

    defaultsApplied.current = true;
    const next = new URLSearchParams(searchParams);
    writeDateParams(next, newestDate ?? new Date());
    if (!next.has("range")) {
      next.set("range", "30");
    }
    setSearchParams(next, { replace: true });
  }, [latestMemories.isPending, newestDate, searchParams, setSearchParams]);

  const updateParams = useCallback(
    (update: (params: URLSearchParams) => void) => {
      navigated.current = true;
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          update(next);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handleAnchorChange = (date: Date) => {
    updateParams((next) => {
      writeDateParams(next, date);
    });
  };

  const handleShift = (days: number) => {
    updateParams((next) => {
      writeDateParams(next, addDays(anchor, days));
    });
  };

  const handleRangeChange = (nextRange: number) => {
    updateParams((next) => {
      writeDateParams(next, anchor);
      next.set("range", String(nextRange));
    });
  };

  const handleHistoryChange = (enabled: boolean) => {
    updateParams((next) => {
      writeDateParams(next, anchor);
      if (enabled) {
        next.set("include_history", "true");
      } else {
        next.delete("include_history");
      }
    });
  };

  const handleDemoSeason = () => {
    updateParams((next) => {
      writeDateParams(next, DEMO_SEASON_ANCHOR);
      next.set("range", String(DEMO_SEASON_RANGE));
      next.delete("include_history");
    });
  };

  const timeline = useReadTimeline({
    year: anchor.getFullYear(),
    month: anchor.getMonth() + 1,
    day: anchor.getDate(),
    day_range: range,
    include_history: includeHistory,
  });

  const data = timeline.data;
  const events = data?.events ?? [];
  const endpoint = `/api/v1/timeline?year=${anchor.getFullYear()}&month=${anchor.getMonth() + 1}&day=${anchor.getDate()}&day_range=${range}&include_history=${includeHistory}`;

  let timelineContent: ReactNode = null;
  if (data) {
    if (data.events.length > 0) {
      timelineContent = <TimelineRail events={events} skips={data.skips} />;
    } else {
      timelineContent = (
        <EmptyState
          icon="timeline"
          eyebrow="No events in this window"
          title="No rings in this range."
          description={
            data.total === 0
              ? `The timeline endpoint returned no events for ${caption}. Total is 0, and the density strip is empty because there are no memories, summaries, or file updates in this window. Move the anchor, widen the range, or load the demo season.`
              : `The endpoint counted ${data.total} events for ${caption} but sampled none. The density array is empty, so there is nothing to plot.`
          }
          endpoint={endpoint}
          method="GET"
          className="timeline-empty"
          action={
            <div className="timeline-empty__actions">
              <Button variant="ink" size="sm" onClick={handleDemoSeason}>
                <Icon name="ring" size={15} />
                Try the demo season
              </Button>
              <Button variant="ghost" size="sm" onClick={() => handleAnchorChange(new Date())}>
                Jump to today
              </Button>
            </div>
          }
        />
      );
    }
  }

  return (
    <div className="page timeline-page">
      <PageHeader
        eyebrow="Timeline · sparse sampling"
        title="Read time in rings."
        description="Five anchors per event kind keep the shape of a season without returning every leaf. Gaps stay honest: each sampled pair records how many memories, summaries, and file changes were omitted."
        meta={<span>{caption}</span>}
        actions={<Badge tone="ochre">5 anchors / kind</Badge>}
      />

      <TimelineControls
        anchor={anchor}
        range={range}
        includeHistory={includeHistory}
        caption={caption}
        onAnchorChange={handleAnchorChange}
        onShift={handleShift}
        onRangeChange={handleRangeChange}
        onHistoryChange={handleHistoryChange}
        onDemoSeason={handleDemoSeason}
      />

      {data ? <TimelineDensity data={data} caption={caption} /> : null}

      <div className="timeline-layout">
        <div className="timeline-layout__main">
          <QueryState
            loading={timeline.isPending}
            error={timeline.error}
            loadingLabel="Reading the timeline rings"
          >
            {timelineContent}
          </QueryState>
        </div>

        <aside className="timeline-layout__side">
          <SummaryPanel
            key={`${anchor.getTime()}-${range}-${includeHistory ? "history" : "current"}`}
            rangeStart={data?.range_start ?? null}
            rangeEnd={data?.range_end ?? null}
            caption={caption}
            disabled={!data || data.total === 0}
          />
          <MemoryComposer />
        </aside>
      </div>
    </div>
  );
}
