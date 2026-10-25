import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueries } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import type {
  TimelineEventSchema,
  TimelineResponseSchema,
} from "../generated-apis-types/schemas";

import { Button } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import {
  MemoryDeprecateDialog,
  MemoryEditDialog,
  type MemoryActionTarget,
} from "../memory/component/MemoryActionDialogs";
import { useListMemories } from "../generated-apis-types/memories/memories";
import {
  getReadTimelineQueryOptions,
  useReadTimeline,
} from "../generated-apis-types/timeline/timeline";
import { formatNumber } from "../../lib/format";

import { TimelineControls } from "./component/TimelineControls";
import { TimelineDensity } from "./component/TimelineDensity";
import { TimelineHeader } from "./component/TimelineHeader";
import {
  TimelineSentinel,
  TimelineSpine,
  buildWindowView,
  earlierWindowLabel,
  type SentinelState,
  type TimelineWindowView,
} from "./component/TimelineSpine";
import { TimelineErrorState, TimelineSkeleton } from "./component/TimelineStates";
import {
  DEMO_SEASON_ANCHOR,
  DEMO_SEASON_RANGE,
  addDays,
  formatDotRange,
  formatRangeCaption,
  isWithinApiRange,
  parseDateParams,
  readHistoryParam,
  readRangeParam,
  startOfDay,
  toDateInput,
  writeDateParams,
  writeHistoryParam,
  writeRangeParam,
} from "./component/helpers";
import "./timeline.css";

interface EarlierState {
  readonly key: string;
  readonly anchors: readonly Date[];
}

interface UrlDefaultsInput {
  readonly searchParams: URLSearchParams;
  readonly setSearchParams: ReturnType<typeof useSearchParams>[1];
  readonly urlDate: Date | null;
  readonly memoriesPending: boolean;
  readonly newestDate: Date | null;
  readonly fallbackDay: Date;
  readonly range: number;
  readonly includeHistory: boolean;
}

function writeWindowParams(
  params: URLSearchParams,
  anchor: Date,
  range: number,
  includeHistory: boolean,
): void {
  writeDateParams(params, anchor);
  writeRangeParam(params, range);
  writeHistoryParam(params, includeHistory);
}

/** Writes the canonical date, `day_range`, and history keys once the anchor is known. */
function useTimelineUrlDefaults({
  searchParams,
  setSearchParams,
  urlDate,
  memoriesPending,
  newestDate,
  fallbackDay,
  range,
  includeHistory,
}: UrlDefaultsInput): void {
  const defaultsApplied = useRef(false);

  useEffect(() => {
    if (defaultsApplied.current) {
      return;
    }
    if (urlDate === null && memoriesPending) {
      return;
    }
    defaultsApplied.current = true;

    const next = new URLSearchParams(searchParams);
    let changed = false;
    if (urlDate === null) {
      writeDateParams(next, newestDate ?? fallbackDay);
      changed = true;
    }
    if (next.get("day_range") !== String(range) || next.has("range")) {
      writeRangeParam(next, range);
      changed = true;
    }
    if (
      (includeHistory && next.get("include_history") !== "true") ||
      (!includeHistory && next.has("include_history"))
    ) {
      writeHistoryParam(next, includeHistory);
      changed = true;
    }
    if (changed) {
      setSearchParams(next, { replace: true });
    }
  }, [
    fallbackDay,
    includeHistory,
    memoriesPending,
    newestDate,
    range,
    searchParams,
    setSearchParams,
    urlDate,
  ]);
}

interface SentinelInput {
  readonly isLoadingEarlier: boolean;
  readonly loadingEarlierLabel: string | null;
  readonly earlierError: unknown;
  readonly earlierErrorLabel: string;
  readonly canLoadEarlier: boolean;
  readonly lastWindowEmpty: boolean;
  readonly lastEarlierLabel: string | null;
  readonly nextEarlierLabel: string;
}

function buildSentinelState({
  isLoadingEarlier,
  loadingEarlierLabel,
  earlierError,
  earlierErrorLabel,
  canLoadEarlier,
  lastWindowEmpty,
  lastEarlierLabel,
  nextEarlierLabel,
}: SentinelInput): SentinelState {
  if (isLoadingEarlier) {
    return { kind: "loading", nextLabel: loadingEarlierLabel ?? nextEarlierLabel };
  }
  if (earlierError) {
    return { kind: "error", nextLabel: earlierErrorLabel, error: earlierError };
  }
  if (!canLoadEarlier) {
    return {
      kind: "exhausted",
      title: "Reached the earliest supported anchor.",
      detail:
        "The next earlier window would end before 1900-01-01, the earliest anchor the API accepts. The current window can still include earlier events because its range extends backward from the anchor.",
      canContinue: false,
    };
  }
  if (lastWindowEmpty) {
    return {
      kind: "exhausted",
      title: `No events in the earlier window (${lastEarlierLabel ?? nextEarlierLabel}).`,
      detail:
        "The archive is quiet this far back. Continue further if you want to search an older window.",
      canContinue: true,
    };
  }
  return { kind: "ready", nextLabel: nextEarlierLabel };
}

function buildEmptyDescription(
  data: TimelineResponseSchema,
  caption: string,
  includeHistory: boolean,
): string {
  if (data.total > 0) {
    return `The archive counted ${formatNumber(data.total)} events in this window but sampled none. Move the window slightly to resample it.`;
  }
  let description = `The archive returned no memories, summaries, or file updates ending in this window (${caption}). Move the window, widen the range, or search the earlier window below.`;
  if (!includeHistory) {
    description +=
      " Deprecated memories are excluded; turn on Include history to widen the read.";
  }
  return description;
}

interface BodyInput {
  readonly awaitingAnchor: boolean;
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: unknown;
  readonly isFetching: boolean;
  readonly onRetry: () => void;
  readonly data: TimelineResponseSchema | undefined;
  readonly anchor: Date;
  readonly onAnchorChange: (date: Date) => void;
  readonly windows: readonly TimelineWindowView[];
  readonly currentEmptyContent: ReactNode;
  readonly isLoadingEarlier: boolean;
  readonly sentinelState: SentinelState;
  readonly onLoadEarlier: () => void;
  readonly onRetryEarlier: () => void;
  readonly onEditMemory: (event: TimelineEventSchema) => void;
  readonly onDeprecateMemory: (event: TimelineEventSchema) => void;
}

function renderTimelineBody({
  awaitingAnchor,
  isPending,
  isError,
  error,
  isFetching,
  onRetry,
  data,
  anchor,
  onAnchorChange,
  windows,
  currentEmptyContent,
  isLoadingEarlier,
  sentinelState,
  onLoadEarlier,
  onRetryEarlier,
  onEditMemory,
  onDeprecateMemory,
}: BodyInput): ReactNode {
  if (awaitingAnchor || (isPending && !data)) {
    return <TimelineSkeleton />;
  }
  if (isError) {
    return <TimelineErrorState error={error} onRetry={onRetry} isRetrying={isFetching} />;
  }
  if (!data) {
    return <TimelineSkeleton />;
  }
  return (
    <>
      <TimelineDensity data={data} anchor={anchor} onAnchorChange={onAnchorChange} />
      <TimelineSpine
        windows={windows}
        currentEmptyContent={currentEmptyContent}
        loadingEarlier={isLoadingEarlier}
        onEditMemory={onEditMemory}
        onDeprecateMemory={onDeprecateMemory}
        sentinel={
          <TimelineSentinel
            state={sentinelState}
            onLoadEarlier={onLoadEarlier}
            onRetry={onRetryEarlier}
          />
        }
      />
    </>
  );
}

/**
 * Sparse timeline: a real date window, a hairline density strip, and a continuous
 * spine of sampled events with honest gap rows. The URL owns the anchor, range,
 * and history switch. "Load earlier" requests the previous API window and appends it.
 */
export function TimelinePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [editTarget, setEditTarget] = useState<MemoryActionTarget | null>(null);
  const [deprecateTarget, setDeprecateTarget] =
    useState<MemoryActionTarget | null>(null);
  const fallbackDay = useMemo(() => startOfDay(new Date()), []);
  const urlDate = useMemo(() => parseDateParams(searchParams), [searchParams]);

  const latestMemories = useListMemories({ limit: 1 });
  const newestMemory = latestMemories.data?.resources[0] ?? null;
  const newestTime = newestMemory?.update_time ?? null;
  const newestDate = useMemo(() => {
    if (!newestTime) {
      return null;
    }
    const parsed = new Date(newestTime);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    const day = startOfDay(parsed);
    return isWithinApiRange(day) ? day : null;
  }, [newestTime]);

  const anchor = useMemo(
    () => urlDate ?? newestDate ?? fallbackDay,
    [urlDate, newestDate, fallbackDay],
  );
  const range = readRangeParam(searchParams);
  const includeHistory = readHistoryParam(searchParams);
  const windowKey = `${toDateInput(anchor)}|${range}|${includeHistory ? "history" : "current"}`;
  const fallbackRangeStart = toDateInput(addDays(anchor, -(range - 1)));

  useTimelineUrlDefaults({
    searchParams,
    setSearchParams,
    urlDate,
    memoriesPending: latestMemories.isPending,
    newestDate,
    fallbackDay,
    range,
    includeHistory,
  });

  const updateParams = useCallback(
    (update: (params: URLSearchParams) => void) => {
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
    updateParams((next) => writeWindowParams(next, date, range, includeHistory));
  };

  const handleShift = (days: number) => {
    const target = addDays(anchor, days);
    if (!isWithinApiRange(target)) {
      return;
    }
    updateParams((next) => writeWindowParams(next, target, range, includeHistory));
  };

  const memoryTarget = (
    event: TimelineEventSchema,
  ): MemoryActionTarget | null => {
    if (event.kind !== "memory" || typeof event.memory_id !== "number") {
      return null;
    }
    return {
      memory_id: event.memory_id,
      title: event.title ?? "",
      content: event.content,
      status: event.status ?? undefined,
    };
  };

  const openEditMemory = (event: TimelineEventSchema) => {
    const target = memoryTarget(event);
    if (target) {
      setEditTarget(target);
    }
  };

  const openDeprecateMemory = (event: TimelineEventSchema) => {
    const target = memoryTarget(event);
    if (target) {
      setDeprecateTarget(target);
    }
  };

  const handleRangeChange = (nextRange: number) => {
    updateParams((next) => writeWindowParams(next, anchor, nextRange, includeHistory));
  };

  const handleHistoryChange = (enabled: boolean) => {
    updateParams((next) => writeWindowParams(next, anchor, range, enabled));
  };

  const handleDemoSeason = () => {
    updateParams((next) =>
      writeWindowParams(next, DEMO_SEASON_ANCHOR, DEMO_SEASON_RANGE, false),
    );
  };

  const handleJumpToday = () => {
    updateParams((next) =>
      writeWindowParams(next, startOfDay(new Date()), range, includeHistory),
    );
  };

  const awaitingAnchor = urlDate === null && latestMemories.isPending;
  const timeline = useReadTimeline(
    {
      year: anchor.getFullYear(),
      month: anchor.getMonth() + 1,
      day: anchor.getDate(),
      day_range: range,
      include_history: includeHistory,
    },
    { query: { enabled: !awaitingAnchor } },
  );
  const data = timeline.data;

  const caption = data
    ? formatRangeCaption(data.range_start, data.range_end)
    : formatRangeCaption(fallbackRangeStart, toDateInput(anchor));
  const rangeLabel = data
    ? formatDotRange(data.range_start, data.range_end)
    : formatDotRange(fallbackRangeStart, toDateInput(anchor));

  const [earlierState, setEarlierState] = useState<EarlierState>({
    key: windowKey,
    anchors: [],
  });
  const earlierAnchors = earlierState.key === windowKey ? earlierState.anchors : [];
  const nextEarlierAnchor = addDays(anchor, -range * (earlierAnchors.length + 1));
  const canLoadEarlier = isWithinApiRange(nextEarlierAnchor);
  const nextEarlierLabel = earlierWindowLabel(anchor, range, earlierAnchors.length);

  const earlierQueryOptions = earlierAnchors.map((date) =>
    getReadTimelineQueryOptions({
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      day: date.getDate(),
      day_range: range,
      include_history: includeHistory,
    }),
  );
  const earlierQueries = useQueries({ queries: earlierQueryOptions });

  const isLoadingEarlier = earlierQueries.some(
    (query) => query.isPending || query.isFetching,
  );
  const loadingEarlierIndex = earlierQueries.findIndex(
    (query) => query.isPending || query.isFetching,
  );
  const loadingEarlierLabel =
    loadingEarlierIndex >= 0
      ? earlierWindowLabel(anchor, range, loadingEarlierIndex)
      : null;
  const earlierErrorIndex = earlierQueries.findIndex((query) => query.isError);
  const earlierError = earlierErrorIndex >= 0 ? earlierQueries[earlierErrorIndex].error : null;
  const earlierErrorLabel =
    earlierErrorIndex >= 0 ? earlierWindowLabel(anchor, range, earlierErrorIndex) : nextEarlierLabel;
  const latestEarlierQuery =
    earlierQueries.length > 0 ? earlierQueries[earlierQueries.length - 1] : null;
  const lastWindowEmpty = Boolean(
    latestEarlierQuery?.data && latestEarlierQuery.data.total === 0,
  );
  const lastEarlierLabel =
    earlierAnchors.length > 0
      ? earlierWindowLabel(anchor, range, earlierAnchors.length - 1)
      : null;

  const handleLoadEarlier = () => {
    setEarlierState((previous) => {
      const anchors = previous.key === windowKey ? previous.anchors : [];
      const nextAnchor = addDays(anchor, -range * (anchors.length + 1));
      if (!isWithinApiRange(nextAnchor)) {
        return { key: windowKey, anchors };
      }
      return { key: windowKey, anchors: [...anchors, nextAnchor] };
    });
  };

  const handleRetryEarlier = () => {
    const query = earlierErrorIndex >= 0 ? earlierQueries[earlierErrorIndex] : null;
    if (query) {
      void query.refetch();
    }
  };

  const sentinelState = buildSentinelState({
    isLoadingEarlier,
    loadingEarlierLabel,
    earlierError,
    earlierErrorLabel,
    canLoadEarlier,
    lastWindowEmpty,
    lastEarlierLabel,
    nextEarlierLabel,
  });

  const earlierWindows: TimelineWindowView[] = earlierAnchors.flatMap((date, index) => {
    const queryData = earlierQueries[index]?.data;
    if (!queryData) {
      return [];
    }
    return [
      buildWindowView({
        key: `earlier-${toDateInput(date)}`,
        data: queryData,
        isCurrent: false,
      }),
    ];
  });

  const currentWindow =
    data && data.events.length > 0
      ? buildWindowView({ key: `current-${windowKey}`, data, isCurrent: true })
      : null;
  const windows = currentWindow ? [currentWindow, ...earlierWindows] : earlierWindows;

  const currentEmptyContent =
    data && data.events.length === 0 ? (
      <EmptyState
        icon="timeline"
        eyebrow="Window is quiet"
        title="No rings in this window."
        description={buildEmptyDescription(data, caption, includeHistory)}
        className="timeline-empty-state"
        action={
          <div className="timeline-empty-actions">
            <Button variant="ink" size="sm" onClick={handleDemoSeason}>
              <Icon name="ring" size={14} />
              Try demo season
            </Button>
            <Button variant="secondary" size="sm" onClick={handleJumpToday}>
              Jump to today
            </Button>
          </div>
        }
      />
    ) : undefined;

  return (
    <div className="content-container timeline-page">
      <TimelineHeader
        rangeLabel={rangeLabel}
        isFetching={timeline.isFetching || awaitingAnchor}
      />
      <TimelineControls
        anchor={anchor}
        range={range}
        includeHistory={includeHistory}
        canGoEarlier={isWithinApiRange(addDays(anchor, -range))}
        canGoLater={isWithinApiRange(addDays(anchor, range))}
        onAnchorChange={handleAnchorChange}
        onShift={handleShift}
        onRangeChange={handleRangeChange}
        onHistoryChange={handleHistoryChange}
        onDemoSeason={handleDemoSeason}
      />
      <div className="timeline-body">
        {renderTimelineBody({
          awaitingAnchor,
          isPending: timeline.isPending,
          isError: timeline.isError,
          error: timeline.error,
          isFetching: timeline.isFetching,
          onRetry: () => {
            void timeline.refetch();
          },
          data,
          anchor,
          onAnchorChange: handleAnchorChange,
          windows,
          currentEmptyContent,
          isLoadingEarlier,
          sentinelState,
          onLoadEarlier: handleLoadEarlier,
          onRetryEarlier: handleRetryEarlier,
          onEditMemory: openEditMemory,
          onDeprecateMemory: openDeprecateMemory,
        })}
      </div>

      {editTarget ? (
        <MemoryEditDialog
          memory={editTarget}
          onClose={() => setEditTarget(null)}
        />
      ) : null}
      {deprecateTarget ? (
        <MemoryDeprecateDialog
          memory={deprecateTarget}
          onClose={() => setDeprecateTarget(null)}
        />
      ) : null}
    </div>
  );
}
