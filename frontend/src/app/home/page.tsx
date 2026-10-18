import { Fragment, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import {
  useGetAiStatus,
  useGetStats,
  useGetTree,
  useListMemories,
  useReadTimeline,
  useSeedDemo,
} from "../generated-apis-types";
import type {
  MemorySchema,
  ReadTimelineParams,
  StatsSchema,
  TimelineEventSchema,
  TreeNodeSchema,
  TreeSchema,
} from "../generated-apis-types/schemas";
import { Badge } from "../component/Badge";
import { Button, ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { Panel } from "../component/Panel";
import { SearchField } from "../component/SearchField";
import { SectionHeading } from "../component/SectionHeading";
import { StatCard } from "../component/StatCard";
import { useToast } from "../component/Toast";
import { ToolCard } from "../component/ToolCard";
import { TreeMark } from "../component/TreeMark";
import { TreeRings } from "../component/TreeRings";
import {
  basename,
  formatBytes,
  formatDate,
  formatNumber,
  formatTime,
  parentPath,
  truncate,
} from "../../lib/format";
import {
  demoAskCitations,
  demoTools,
  type StatAccent,
} from "../type/demo";
import type { BadgeTone } from "../type/ui";
import "./home.css";

const SEARCH_SUGGESTIONS = [
  "hybrid retrieval",
  "superseded memories",
  "/history/industry",
  "Ford in the 1970s",
] as const;

const MEMORY_PREVIEW_LIMIT = 4;
const TIMELINE_WINDOW_DAYS = 14;
const LATEST_EVENT_LIMIT = 3;
const FILE_PREVIEW_LIMIT = 4;
const EMPTY_MEMORIES: readonly MemorySchema[] = [];
const EMPTY_TREE_NODES: readonly TreeNodeSchema[] = [];
const EMPTY_EVENTS: readonly TimelineEventSchema[] = [];

const TIMELINE_KIND_LABELS: Record<TimelineEventSchema["kind"], string> = {
  memory: "Memory",
  summary: "Summary",
  file_update: "File",
};

const TIMELINE_KIND_TONES: Record<TimelineEventSchema["kind"], BadgeTone> = {
  memory: "moss",
  summary: "ochre",
  file_update: "neutral",
};

interface StatCardData {
  readonly label: string;
  readonly value: string;
  readonly note: string;
  readonly accent: StatAccent;
}

interface ChainNode {
  readonly id: number;
  readonly status: MemorySchema["status"];
}

interface SupersedeChain {
  readonly nodes: readonly ChainNode[];
  readonly anchorId: number | null;
}

interface TimelineSummary {
  readonly sampled: number;
  readonly total: number;
  readonly skipped: number;
}

function searchHref(query: string): string {
  return `/search?query=${encodeURIComponent(query)}`;
}

function statNote(stats: StatsSchema | undefined, error: boolean, loaded: string): string {
  if (stats) {
    return loaded;
  }
  return error ? "Counts unavailable" : "Reading live counts";
}

function statsCredit(stats: StatsSchema | undefined, error: boolean): string {
  if (stats) {
    return "Live counts · /api/v1/stats";
  }
  return error ? "Counts unavailable" : "Reading live counts";
}

function archiveCondition(stats: StatsSchema | undefined, error: boolean): string {
  if (stats) {
    return "Live archive";
  }
  return error ? "API unreachable" : "Reading the archive";
}

function footerCount(stats: StatsSchema | undefined): string {
  if (!stats) {
    return "Local-first archive";
  }
  return `${formatNumber(stats.memory_count)} memories · ${formatNumber(stats.file_count)} files`;
}

function fileStatNote(stats: StatsSchema | undefined): string {
  return stats ? `${formatBytes(stats.storage_bytes)} stored locally` : "";
}

function memoryStatNote(stats: StatsSchema | undefined): string {
  if (!stats) {
    return "";
  }
  return `${formatNumber(stats.active_memory_count)} active · ${formatNumber(stats.memory_count)} pressed`;
}

function buildStatCards(
  stats: StatsSchema | undefined,
  error: boolean,
): readonly StatCardData[] {
  return [
    {
      label: "Files archived",
      value: stats ? formatNumber(stats.file_count) : "—",
      note: statNote(stats, error, fileStatNote(stats)),
      accent: "moss",
    },
    {
      label: "Memories pressed",
      value: stats ? formatNumber(stats.active_memory_count) : "—",
      note: statNote(stats, error, memoryStatNote(stats)),
      accent: "ochre",
    },
    {
      label: "AI summaries",
      value: stats ? formatNumber(stats.summary_count) : "—",
      note: statNote(stats, error, "generator recorded on every one"),
      accent: "vermilion",
    },
    {
      label: "Indexed chunks",
      value: stats ? formatNumber(stats.chunk_count) : "—",
      note: statNote(stats, error, "current chunks · 1-based"),
      accent: "ink",
    },
  ];
}

function memoryTitle(memory: MemorySchema): string {
  const compact = memory.content.replace(/\s+/g, " ").trim();
  if (compact.length === 0) {
    return `Memory #${memory.memory_id}`;
  }
  const sentenceEnd = compact.search(/[.!?\u3002\uFF01\uFF1F]/);
  const sentence = sentenceEnd >= 0 ? compact.slice(0, sentenceEnd + 1) : compact;
  return truncate(sentence, 118) || `Memory #${memory.memory_id}`;
}

function memoryExcerpt(memory: MemorySchema): string {
  const compact = memory.content.replace(/\s+/g, " ").trim();
  return compact.length > 0 ? truncate(compact, 280) : "No content recorded.";
}

function memoryStatusTone(status: MemorySchema["status"]): BadgeTone {
  return status === "active" ? "moss" : "ochre";
}

function buildSupersedeChain(memories: readonly MemorySchema[]): SupersedeChain {
  for (const memory of memories) {
    if (memory.supersedes_ids.length > 0) {
      const nodes = memory.supersedes_ids.map<ChainNode>((id) => ({
        id,
        status: "deprecated",
      }));
      nodes.push({ id: memory.memory_id, status: memory.status });
      return { nodes, anchorId: memory.memory_id };
    }
    if (memory.superseded_by_id !== null) {
      return {
        nodes: [
          { id: memory.memory_id, status: memory.status },
          { id: memory.superseded_by_id, status: "active" },
        ],
        anchorId: memory.superseded_by_id,
      };
    }
  }
  return { nodes: [], anchorId: null };
}

function chainNodeClass(status: MemorySchema["status"]): string {
  return status === "active"
    ? "supersede-chain__node is-active"
    : "supersede-chain__node is-deprecated";
}

function currentFiles(nodes: readonly TreeNodeSchema[]): TreeNodeSchema[] {
  return nodes
    .filter((node) => node.kind === "file" && node.is_current)
    .sort((left, right) => Date.parse(right.update_time) - Date.parse(left.update_time));
}

function timelineParamsFor(value: string | undefined): ReadTimelineParams | null {
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

function latestEvents(events: readonly TimelineEventSchema[]): TimelineEventSchema[] {
  return [...events]
    .sort((left, right) => Date.parse(right.time) - Date.parse(left.time))
    .slice(0, LATEST_EVENT_LIMIT);
}

function timelineCountLabel(summary: TimelineSummary | undefined): string {
  if (!summary) {
    return "—";
  }
  const base = `${formatNumber(summary.sampled)} sampled / ${formatNumber(summary.total)} events`;
  return summary.skipped > 0 ? `${base} · ${formatNumber(summary.skipped)} skipped` : base;
}

function eventKey(event: TimelineEventSchema): string {
  const source =
    event.memory_id ?? event.memory_summary_id ?? event.file_id ?? event.raw_file_path ?? "event";
  return `${event.kind}-${String(source)}-${event.time}`;
}

function aiHeading(
  pending: boolean,
  error: boolean,
  configured: boolean,
  provider: string | undefined,
  model: string | undefined,
): string {
  if (pending) {
    return "Grounded answers · reading AI status";
  }
  if (error) {
    return "Grounded answers · status unavailable";
  }
  if (configured && provider && model) {
    return `Grounded answers · ${provider} ${model}`;
  }
  return "Grounded answers · AI unconfigured";
}

function aiDotClassName(pending: boolean, configured: boolean): string {
  if (pending) {
    return "status-dot status-dot--pending";
  }
  return configured ? "status-dot" : "status-dot status-dot--missing";
}

function aiFallbackCopy(configured: boolean, pending: boolean): string {
  if (pending) {
    return "Reading the AI connection. Answers cite retrieval or fail honestly.";
  }
  if (configured) {
    return "Cited answers via DeepSeek. Only retrieved passages leave this machine; the key never reaches the browser.";
  }
  return "No API key? Ask returns 503 ai_not_configured, never a fabricated answer. Set DENDRO_DEEPSEEK_API_KEY in .secrets/deepseek.env.";
}

function aiHintCopy(configured: boolean, pending: boolean): string {
  if (pending) {
    return "Checking the AI connection";
  }
  return configured ? "RAG · 2–4 retrieval steps" : "AI unconfigured · summaries stay extractive";
}

function MemoryLedgerSkeleton() {
  return (
    <div className="memory-ledger" aria-busy="true" aria-label="Reading recent memories">
      {[0, 1, 2].map((index) => (
        <div className="memory-entry home-skeleton-entry" key={index} aria-hidden="true">
          <div className="memory-entry__rail">
            <span className="home-skeleton home-skeleton--tiny" />
            <span className="home-skeleton home-skeleton--tiny is-short" />
          </div>
          <div className="memory-entry__body">
            <span className="home-skeleton home-skeleton--badge" />
            <span className="home-skeleton home-skeleton--title" />
            <span className="home-skeleton home-skeleton--line" />
            <span className="home-skeleton home-skeleton--line is-short" />
          </div>
        </div>
      ))}
    </div>
  );
}

function LineageSkeleton() {
  return (
    <div className="lineage-card__files" aria-busy="true" aria-label="Reading current file leaves">
      {[0, 1, 2].map((index) => (
        <div className="lineage-file home-skeleton-entry" key={index} aria-hidden="true">
          <span className="lineage-file__graft" />
          <span className="lineage-file__icon">
            <span className="home-skeleton home-skeleton--icon" />
          </span>
          <span className="lineage-file__copy">
            <span className="home-skeleton home-skeleton--name" />
            <span className="home-skeleton home-skeleton--meta" />
          </span>
          <span className="home-skeleton home-skeleton--badge" />
        </div>
      ))}
    </div>
  );
}

function SeasonSkeleton() {
  return (
    <div className="season-strip__events" aria-busy="true" aria-label="Reading the latest season">
      {[0, 1, 2].map((index) => (
        <div className="season-event" key={index} aria-hidden="true">
          <span className="home-skeleton home-skeleton--badge" />
          <span className="home-skeleton home-skeleton--line" />
          <span className="home-skeleton home-skeleton--line is-short" />
        </div>
      ))}
    </div>
  );
}

function SeedPanel({
  isPending,
  onSeed,
}: {
  readonly isPending: boolean;
  readonly onSeed: () => void;
}) {
  return (
    <Panel
      eyebrow="First pressing"
      title="Seed the demo archive."
      action={<Badge tone="ochre" dot>Archive empty</Badge>}
      tone="moss"
      className="seed-panel reveal reveal-5"
    >
      <div className="seed-panel__layout">
        <div>
          <p className="seed-panel__lede">
            The shelves are ready but empty. Seed a small, coherent archive of text
            files, memories, and one summary, then watch the tree and the timeline
            fill in. The seed only writes to an empty archive.
          </p>
          <ul className="seed-panel__facts">
            <li>Text files with paths</li>
            <li>Memory supersession</li>
            <li>One generated summary</li>
            <li>Nothing overwritten</li>
          </ul>
        </div>
        <div className="seed-panel__actions">
          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={onSeed}
            disabled={isPending}
          >
            <Icon name="leaf" size={16} />
            {isPending ? "Seeding the archive…" : "Seed the demo archive"}
          </Button>
          <ButtonLink to="/library" variant="ghost" size="sm">
            Upload files instead
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
          <p className="seed-panel__hint">
            Seeding uses POST /api/v1/demo/seed. Counts and recent records refresh
            when it finishes.
          </p>
        </div>
      </div>
    </Panel>
  );
}

function StatsStrip({
  stats,
  error,
  pending,
}: {
  readonly stats: StatsSchema | undefined;
  readonly error: boolean;
  readonly pending: boolean;
}) {
  return (
    <section
      className="stats-strip reveal reveal-5"
      aria-label="Archive statistics"
      aria-busy={pending}
    >
      <div className="stats-strip__head">
        <p className="eyebrow">The archive in numbers</p>
        <p className="stats-strip__credit">{statsCredit(stats, error)}</p>
      </div>
      <div className="stats-strip__grid">
        {buildStatCards(stats, error).map((stat, index) => (
          <StatCard
            key={stat.label}
            label={stat.label}
            value={stat.value}
            note={stat.note}
            accent={stat.accent}
            index={String(index + 1).padStart(2, "0")}
            className="reveal"
          />
        ))}
      </div>
    </section>
  );
}

function MemoryGrain({
  pending,
  error,
  memories,
}: {
  readonly pending: boolean;
  readonly error: boolean;
  readonly memories: readonly MemorySchema[];
}) {
  if (pending) {
    return <MemoryLedgerSkeleton />;
  }
  if (error) {
    return (
      <p className="home-inline-note">
        The recent grain did not answer. <Link to="/settings">Check the archive connection.</Link>
      </p>
    );
  }
  if (memories.length === 0) {
    return (
      <div className="home-empty-note">
        <p className="eyebrow">No memories pressed yet</p>
        <p>
          The grain begins with a single moment. Press a memory, or seed the demo archive
          above to see how memories gather over time.
        </p>
        <ButtonLink to="/memory/new" variant="ink" size="sm">
          Press a memory
          <Icon name="arrow-right" size={15} />
        </ButtonLink>
      </div>
    );
  }
  return (
    <div className="memory-ledger">
      {memories.map((memory) => (
        <article className="memory-entry" key={memory.memory_id}>
          <div className="memory-entry__rail">
            <time dateTime={memory.update_time}>{formatDate(memory.update_time)}</time>
            <span>{formatTime(memory.update_time)}</span>
            <span className="memory-entry__pin" aria-hidden="true" />
          </div>
          <div className="memory-entry__body">
            <div className="memory-entry__meta">
              <Badge tone={memoryStatusTone(memory.status)} dot>
                {memory.status}
              </Badge>
              <span className="memory-entry__id">MEMORY #{memory.memory_id}</span>
            </div>
            <h3>{memoryTitle(memory)}</h3>
            <p>{memoryExcerpt(memory)}</p>
            <div className="memory-entry__foot">
              <span className="theme-list">
                <span>source: {memory.source}</span>
                {memory.supersedes_ids.length > 0 ? (
                  <span>supersedes {memory.supersedes_ids.length}</span>
                ) : null}
                {memory.superseded_by_id !== null ? (
                  <span>superseded by #{memory.superseded_by_id}</span>
                ) : null}
              </span>
              <Link
                className="memory-entry__link"
                to={`/memory/${memory.memory_id}`}
              >
                Read memory
                <Icon name="arrow-right" size={13} />
              </Link>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function GrainNote({ chain }: { readonly chain: SupersedeChain }) {
  const nodes = chain.nodes.slice(-4);
  return (
    <aside className="grain-note">
      <span className="grain-note__quote-icon" aria-hidden="true">
        <Icon name="quote" size={22} />
      </span>
      <p className="eyebrow">Retrieval note</p>
      <p className="grain-note__quote">
        A superseded memory leaves search. It never leaves the record.
      </p>
      {nodes.length > 0 ? (
        <div className="supersede-chain" aria-label="Supersede chain from recent memories">
          {nodes.map((node, index) => (
            <Fragment key={`${node.id}-${index}`}>
              {index > 0 ? <span className="supersede-chain__line" aria-hidden="true" /> : null}
              <span className={chainNodeClass(node.status)}>memory:{node.id}</span>
            </Fragment>
          ))}
        </div>
      ) : (
        <p className="grain-note__empty">
          No supersession appears in the latest grain. Every memory keeps its own leaf.
        </p>
      )}
      {chain.anchorId !== null ? (
        <p className="grain-note__code">
          GET /api/v1/memories/{chain.anchorId}?trace_history=true
        </p>
      ) : null}
    </aside>
  );
}

function SeasonStrip({
  latestPending,
  latestError,
  latestMemory,
  timelinePending,
  timelineError,
  events,
  summary,
}: {
  readonly latestPending: boolean;
  readonly latestError: boolean;
  readonly latestMemory: MemorySchema | undefined;
  readonly timelinePending: boolean;
  readonly timelineError: boolean;
  readonly events: readonly TimelineEventSchema[];
  readonly summary: TimelineSummary | undefined;
}) {
  let body: ReactNode;
  if (latestPending) {
    body = <SeasonSkeleton />;
  } else if (latestError) {
    body = (
      <p className="season-strip__empty">
        The season anchor could not be read. Check the archive connection.
      </p>
    );
  } else if (!latestMemory) {
    body = (
      <p className="season-strip__empty">
        No memories are pressed yet, so there is no season to sample. The window
        begins with the first memory.
      </p>
    );
  } else if (timelinePending) {
    body = <SeasonSkeleton />;
  } else if (timelineError) {
    body = (
      <p className="season-strip__empty">
        The timeline did not answer for this window. Try again from the timeline view.
      </p>
    );
  } else if (events.length === 0) {
    body = (
      <p className="season-strip__empty">
        No events were sampled in the fourteen days ending {formatDate(latestMemory.update_time)}.
      </p>
    );
  } else {
    body = (
      <div className="season-strip__events">
        {events.map((event, index) => {
          const content =
            event.content.trim().length > 0
              ? truncate(event.content, 160)
              : "No excerpt recorded.";
          return (
            <article className="season-event" key={`${eventKey(event)}-${index}`}>
              <div className="season-event__top">
                <Badge tone={TIMELINE_KIND_TONES[event.kind]} dot>
                  {TIMELINE_KIND_LABELS[event.kind]}
                </Badge>
                <time className="season-event__time" dateTime={event.time}>
                  {formatDate(event.time)} · {formatTime(event.time)}
                </time>
              </div>
              <p className="season-event__content">{content}</p>
              <span className="season-event__anchor">anchor {event.anchor.toFixed(2)}</span>
            </article>
          );
        })}
      </div>
    );
  }

  return (
    <div className="season-strip reveal reveal-4">
      <div className="season-strip__head">
        <div>
          <p className="eyebrow">Latest season · {TIMELINE_WINDOW_DAYS} days</p>
          <p className="season-strip__range">
            {latestMemory
              ? `Sampled around ${formatDate(latestMemory.update_time)}`
              : "Waiting for the first memory to anchor the window"}
          </p>
        </div>
        <span className="season-strip__count">{timelineCountLabel(summary)}</span>
      </div>
      {body}
    </div>
  );
}

function LineageFiles({
  pending,
  error,
  files,
}: {
  readonly pending: boolean;
  readonly error: boolean;
  readonly files: readonly TreeNodeSchema[];
}) {
  if (pending) {
    return <LineageSkeleton />;
  }
  if (error) {
    return (
      <div className="lineage-card__files">
        <p className="home-inline-note">
          The tree did not answer. <Link to="/settings">Check the archive connection.</Link>
        </p>
      </div>
    );
  }
  if (files.length === 0) {
    return (
      <div className="lineage-card__files">
        <div className="home-empty-note">
          <p className="eyebrow">No file leaves in this branch</p>
          <p>
            Upload a file to grow the first branch. Re-uploading the same path will
            grow a new leaf while the old edition stays traceable.
          </p>
          <ButtonLink to="/library" variant="ink" size="sm">
            Upload a file
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
        </div>
      </div>
    );
  }
  return (
    <div className="lineage-card__files">
      {files.map((file) => (
        <div className="lineage-file" key={file.id}>
          <span className="lineage-file__graft" aria-hidden="true" />
          <span className="lineage-file__icon" aria-hidden="true">
            <Icon name="file" size={18} />
          </span>
          <span className="lineage-file__copy">
            <span className="lineage-file__name" title={file.path}>
              {file.name || basename(file.path)}
            </span>
            <span className="lineage-file__path" title={file.path}>
              {file.path}
            </span>
            <span className="lineage-file__meta">
              <span>file:{file.file_id ?? "—"}</span>
              <span>Updated {formatDate(file.update_time)}</span>
            </span>
          </span>
          <Badge tone="moss" dot>
            current leaf
          </Badge>
        </div>
      ))}
    </div>
  );
}

function LineageSection({
  pending,
  error,
  tree,
  files,
  stats,
}: {
  readonly pending: boolean;
  readonly error: boolean;
  readonly tree: TreeSchema | undefined;
  readonly files: readonly TreeNodeSchema[];
  readonly stats: StatsSchema | undefined;
}) {
  const leadFile = files.at(0);
  const root = tree?.root ?? "/";
  const branch = leadFile ? parentPath(leadFile.path) : "/";
  return (
    <section className="home-section" aria-labelledby="lineage-title">
      <SectionHeading
        index="02"
        eyebrow="The branching shelf"
        title="Every path remembers its previous editions."
        id="lineage-title"
        action={
          <ButtonLink to="/tree" variant="ghost" size="sm">
            Walk the tree
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
        }
      />
      <div className="lineage-card">
        <div className="lineage-card__path">
          <p className="eyebrow">Current branch</p>
          <div className="path-breadcrumb">
            <Icon name="folder" size={17} />
            <span>{root}</span>
            {branch !== "/" ? (
              <>
                <span className="path-breadcrumb__slash" aria-hidden="true">/</span>
                <span>{branch.replace(/^\//, "")}</span>
              </>
            ) : null}
          </div>
          <p className="lineage-card__path-note">
            A re-upload grows a new leaf. The old branch stays indexed as history and
            returns only when you ask for it.
            {tree?.truncated
              ? " This preview stops at depth four; open the tree for the rest."
              : ""}
          </p>
          <div className="lineage-card__legend">
            <span><i className="legend-dot legend-dot--current" aria-hidden="true" />Current</span>
            <span><i className="legend-dot legend-dot--history" aria-hidden="true" />History on request</span>
          </div>
          <div className="lineage-card__meta">
            <span>{tree ? `${formatNumber(files.length)} leaves in view` : "— leaves in view"}</span>
            <span aria-hidden="true">/</span>
            <span>
              {stats ? `${formatNumber(stats.chunk_count)} chunks indexed` : "— chunks indexed"}
            </span>
            <span aria-hidden="true">/</span>
            <span>include_history=false</span>
          </div>
        </div>
        <LineageFiles pending={pending} error={error} files={files} />
      </div>
    </section>
  );
}

function AskSection({
  configured,
  pending,
  error,
  provider,
  model,
}: {
  readonly configured: boolean;
  readonly pending: boolean;
  readonly error: boolean;
  readonly provider: string | undefined;
  readonly model: string | undefined;
}) {
  const heading = aiHeading(pending, error, configured, provider, model);
  const dotClass = aiDotClassName(pending, configured);
  return (
    <section className="home-section" aria-labelledby="ask-title">
      <div className="ask-banner">
        <div className="ask-banner__rings" aria-hidden="true">
          <TreeRings variant="cta" />
        </div>
        <div className="ask-banner__copy">
          <p className="eyebrow">
            <span className={dotClass} aria-hidden="true" />
            {heading}
          </p>
          <h2 id="ask-title">Let the rings answer.</h2>
          <p>
            Ask across every file, memory, and summary. Each claim returns with a
            citation, or it does not return at all.
          </p>
          <div className="ask-banner__actions">
            <ButtonLink to="/ask" variant="paper" size="md">
              Open the reading room
              <Icon name="arrow-up-right" size={16} />
            </ButtonLink>
            <span className="ask-banner__hint">
              {aiHintCopy(configured, pending)}
            </span>
          </div>
        </div>
        <div className="ask-banner__citations" aria-label="Example citation formats">
          <p className="eyebrow">Every answer carries its grain</p>
          <div className="citation-stack">
            {demoAskCitations.map((citation) => (
              <span
                className={`citation citation--${citation.tone}`}
                key={citation.label}
              >
                <Icon name={citation.tone === "file" ? "file" : "memory"} size={13} />
                [{citation.label}]
              </span>
            ))}
          </div>
          <p className="ask-banner__fallback">{aiFallbackCopy(configured, pending)}</p>
        </div>
      </div>
    </section>
  );
}

/**
 * The archive's front porch: live counts, recent memory grain, current file
 * leaves, the latest fourteen-day season, the RAG invitation, and the tool shelf.
 */
export function HomePage() {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const statsQuery = useGetStats({ query: { staleTime: 30_000 } });
  const recentQuery = useListMemories(
    { limit: MEMORY_PREVIEW_LIMIT },
    { query: { staleTime: 30_000 } },
  );
  const latestQuery = useListMemories(
    { limit: 1 },
    { query: { staleTime: 60_000 } },
  );
  const treeQuery = useGetTree(
    { root: "/", depth: 4 },
    { query: { staleTime: 60_000 } },
  );
  const aiQuery = useGetAiStatus({ query: { staleTime: 60_000 } });

  const latestMemory = latestQuery.data?.resources.at(0);
  const timelineParams = useMemo(
    () => timelineParamsFor(latestMemory?.update_time),
    [latestMemory],
  );
  const timelineFallback = useMemo(() => fallbackTimelineParams(), []);
  const timelineQuery = useReadTimeline(timelineParams ?? timelineFallback, {
    query: { enabled: timelineParams !== null, staleTime: 60_000 },
  });

  const seedDemo = useSeedDemo({
    mutation: {
      onSuccess: (result) => {
        void queryClient.invalidateQueries();
        const summaryWord = result.summaries_created === 1 ? "summary" : "summaries";
        toast.success(
          `Seeded ${formatNumber(result.files_created)} files, ${formatNumber(result.memories_created)} memories, and ${formatNumber(result.summaries_created)} ${summaryWord}.`,
        );
      },
      onError: (error) => {
        toast.error(
          error instanceof Error ? error.message : "The demo archive could not be seeded.",
        );
      },
    },
  });

  const handleSearch = (value: string) => {
    navigate(value.length > 0 ? searchHref(value) : "/search");
  };

  const stats = statsQuery.data;
  const statsError = statsQuery.isError;
  const memories = recentQuery.data?.resources ?? EMPTY_MEMORIES;
  const treeNodes = treeQuery.data?.nodes ?? EMPTY_TREE_NODES;
  const files = useMemo(() => currentFiles(treeNodes), [treeNodes]);
  const previewFiles = files.slice(0, FILE_PREVIEW_LIMIT);
  const chain = useMemo(() => buildSupersedeChain(memories), [memories]);
  const seasonEvents = useMemo(
    () => latestEvents(timelineQuery.data?.events ?? EMPTY_EVENTS),
    [timelineQuery.data],
  );
  const aiConfigured = aiQuery.data?.configured === true;
  const emptyArchive =
    stats !== undefined && stats.file_count + stats.memory_count === 0;

  return (
    <div className="page home-page">
      <section className="home-hero">
        <div className="home-hero__rings" aria-hidden="true">
          <TreeRings variant="hero" />
        </div>

        <div className="home-hero__main">
          <p className="home-hero__kicker reveal reveal-1">
            <span className="kicker-mark" aria-hidden="true" />
            A local-first memory archive
            <span className="home-hero__kicker-rule" aria-hidden="true" />
            <span>FIELD STATION 001</span>
          </p>

          <h1 className="home-hero__title reveal reveal-2">
            Memory is not data.
            <span className="home-hero__title-span">It is <em>growth.</em></span>
          </h1>

          <p className="home-hero__lede reveal reveal-3">
            A second brain with provenance. Files branch by path, memories gather by
            time, and every answer returns with the grain it came from.
          </p>

          <div className="home-hero__search reveal reveal-4">
            <SearchField
              value={query}
              onChange={setQuery}
              onSubmit={handleSearch}
              size="lg"
              label="Search the DendroMatrix archive"
              placeholder="Search files, memories, paths, or a feeling..."
              submitLabel="Search the rings"
            />
            <div className="search-suggestions">
              <span className="search-suggestions__label">Follow a vein</span>
              {SEARCH_SUGGESTIONS.map((suggestion) => (
                <Link key={suggestion} to={searchHref(suggestion)} className="suggestion">
                  {suggestion}
                </Link>
              ))}
            </div>
          </div>
        </div>

        <aside className="specimen-card reveal reveal-3" aria-label="Archive specimen label">
          <div className="specimen-card__head">
            <span>Herbarium label</span>
            <span>No. 001</span>
          </div>
          <div className="specimen-card__seal">
            <TreeMark size={40} />
            <span className="specimen-card__seal-text">Pressed locally</span>
          </div>
          <p className="specimen-card__species">Dendromatrix memoriae</p>
          <p className="specimen-card__family">Family: Knowledge systems</p>
          <dl className="specimen-card__facts">
            <div>
              <dt>Collected</dt>
              <dd>On this machine</dd>
            </div>
            <div>
              <dt>Habitat</dt>
              <dd>Paths and time</dd>
            </div>
            <div>
              <dt>Instruments</dt>
              <dd>Six tools</dd>
            </div>
            <div>
              <dt>Condition</dt>
              <dd>{archiveCondition(stats, statsError)}</dd>
            </div>
          </dl>
          <p className="specimen-card__note">
            Old branches remain visible. Nothing is overwritten.
          </p>
          <div className="specimen-card__foot">
            <span>DM–001</span>
            <span aria-hidden="true">✦</span>
            <span>2026</span>
          </div>
        </aside>
      </section>

      {emptyArchive ? (
        <SeedPanel
          isPending={seedDemo.isPending}
          onSeed={() => seedDemo.mutate()}
        />
      ) : null}

      <StatsStrip
        stats={stats}
        error={statsError}
        pending={statsQuery.isPending}
      />

      <section className="home-section" aria-labelledby="recent-memory-title">
        <SectionHeading
          index="01"
          eyebrow="The recent grain"
          title="What the archive remembered lately."
          id="recent-memory-title"
          action={
            <ButtonLink to="/timeline" variant="ghost" size="sm">
              Open timeline
              <Icon name="arrow-right" size={15} />
            </ButtonLink>
          }
        />
        <div className="memory-layout">
          <MemoryGrain
            pending={recentQuery.isPending}
            error={recentQuery.isError}
            memories={memories}
          />
          <GrainNote chain={chain} />
        </div>
        <SeasonStrip
          latestPending={latestQuery.isPending}
          latestError={latestQuery.isError}
          latestMemory={latestMemory}
          timelinePending={timelineQuery.isPending}
          timelineError={timelineQuery.isError}
          events={seasonEvents}
          summary={timelineQuery.data}
        />
      </section>

      <LineageSection
        pending={treeQuery.isPending}
        error={treeQuery.isError}
        tree={treeQuery.data}
        files={previewFiles}
        stats={stats}
      />

      <AskSection
        configured={aiConfigured}
        pending={aiQuery.isPending}
        error={aiQuery.isError}
        provider={aiQuery.data?.provider}
        model={aiQuery.data?.model}
      />

      <section className="home-section" aria-labelledby="tool-shelf-title">
        <SectionHeading
          index="03"
          eyebrow="The tool shelf"
          title="Six moves, two to four steps."
          id="tool-shelf-title"
          action={
            <ButtonLink to="/method" variant="ghost" size="sm">
              Read the method
              <Icon name="arrow-right" size={15} />
            </ButtonLink>
          }
        />
        <p className="tool-shelf__intro">
          An LLM should not read the whole library. These are the six focused moves
          that take it from a question to a quoted, traceable passage.
        </p>
        <div className="tool-grid">
          {demoTools.map((tool) => (
            <ToolCard key={tool.name} tool={tool} />
          ))}
        </div>
      </section>

      <footer className="home-colophon">
        <span>DendroMatrix</span>
        <span aria-hidden="true">✦</span>
        <span>{footerCount(stats)}</span>
        <span aria-hidden="true">✦</span>
        <span>Local-first, single reader</span>
      </footer>
    </div>
  );
}
