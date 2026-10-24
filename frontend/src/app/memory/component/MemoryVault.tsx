import { useId, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import {
  getListMemoriesQueryOptions,
  useListMemories,
} from "../../generated-apis-types/memories/memories";
import type { MemorySchema } from "../../generated-apis-types/schemas";
import { useSearchKnowledge } from "../../generated-apis-types/search/search";
import { useGetStats } from "../../generated-apis-types/system/system";
import { useDebouncedValue } from "../../hook/useDebouncedValue";
import { formatDate, formatDateTime, formatNumber } from "../../../lib/format";

import {
  MemoryEmptyState,
  MemoryErrorState,
  MemorySkeleton,
} from "./MemoryStates";
import { MemoryStatus } from "./MemoryStatus";
import { splitMemoryPreview } from "./helpers";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;
const SEARCH_RESULT_LIMIT = 20;
const SEARCH_INPUT_MAX = 200;

type StatusFilter = "all" | "active" | "deprecated";

const STATUS_FILTERS: ReadonlyArray<{ readonly value: StatusFilter; readonly label: string }> = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "deprecated", label: "Superseded" },
];

interface MemoryCardModel {
  readonly memory_id: number;
  readonly content: string;
  readonly status: "active" | "deprecated";
  readonly update_time: string;
  readonly source?: MemorySchema["source"];
  readonly created_at?: string;
  readonly supersedes_ids?: readonly number[];
  readonly superseded_by_id?: number | null;
  readonly score?: number;
  readonly matched_by?: readonly string[];
}

function matchesStatus(memory: MemoryCardModel, filter: StatusFilter): boolean {
  return filter === "all" || memory.status === filter;
}

function filterNoun(filter: StatusFilter): string {
  if (filter === "active") {
    return "active";
  }
  if (filter === "deprecated") {
    return "superseded";
  }
  return "matching";
}

function buildFilterNote(
  filter: StatusFilter,
  searchMode: boolean,
  searchMatchCount: number,
  loadedCount: number,
  hasMore: boolean,
  loading: boolean,
): string | null {
  if (loading || filter === "all") {
    return null;
  }
  if (searchMode) {
    return `The status filter applies to the ${formatNumber(searchMatchCount)} memory matches returned by this search.`;
  }
  return `The status filter applies to the ${formatNumber(loadedCount)} loaded records${hasMore ? "; load older records to widen the scan." : "."}`;
}

function buildSearchNote(searchMode: boolean, searchEnabled: boolean): string | null {
  if (!searchMode || !searchEnabled) {
    return null;
  }
  return `Search is capped at ${SEARCH_RESULT_LIMIT} memory matches and ranked by fused text and vector score. Refine the phrase to narrow the set.`;
}

function MemoryStatusFilter({
  value,
  onChange,
}: {
  readonly value: StatusFilter;
  readonly onChange: (value: StatusFilter) => void;
}) {
  return (
    <div className="tabs tabs--light memory-filter" role="group" aria-label="Filter memories by status">
      {STATUS_FILTERS.map((option) => (
        <button
          key={option.value}
          type="button"
          className={["tab", value === option.value ? "is-active" : null]
            .filter(Boolean)
            .join(" ")}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function SupersedeBanner({ memory }: { readonly memory: MemoryCardModel }) {
  if (memory.status === "deprecated") {
    return (
      <div className="memory-card__banner is-deprecated">
        <span>
          {memory.superseded_by_id !== null && memory.superseded_by_id !== undefined ? (
            <>
              Superseded by{" "}
              <Link to={`/memory/${memory.superseded_by_id}`}>
                CRYSTAL #{memory.superseded_by_id}
              </Link>
              . Kept in the ledger; no longer retrieved.
            </>
          ) : (
            "Superseded and kept in the ledger for provenance."
          )}
        </span>
      </div>
    );
  }
  if (memory.supersedes_ids && memory.supersedes_ids.length > 0) {
    return (
      <div className="memory-card__banner">
        <span>
          Replaces{" "}
          {memory.supersedes_ids.map((id, index) => (
            <span key={id}>
              {index > 0 ? ", " : null}
              <Link to={`/memory/${id}`}>CRYSTAL #{id}</Link>
            </span>
          ))}
          .
        </span>
      </div>
    );
  }
  return null;
}

function MemoryCard({
  memory,
  searchMode = false,
}: {
  readonly memory: MemoryCardModel;
  readonly searchMode?: boolean;
}) {
  const preview = splitMemoryPreview(memory.content);
  const href = `/memory/${memory.memory_id}`;
  return (
    <article
      className={["memory-card", memory.status === "deprecated" ? "is-deprecated" : null]
        .filter(Boolean)
        .join(" ")}
    >
      <header className="memory-card__head">
        <div className="memory-card__ids">
          <Link className="memory-card__id" to={href}>
            CRYSTAL #{memory.memory_id}
          </Link>
          <MemoryStatus status={memory.status} />
        </div>
        <span className="memory-card__epoch">
          Occurred <time dateTime={memory.update_time}>{formatDateTime(memory.update_time)}</time>
        </span>
      </header>

      <h2 className="memory-card__thesis">
        <Link to={href}>{preview.thesis}</Link>
      </h2>
      {preview.body ? <p className="memory-card__body">{preview.body}</p> : null}

      <SupersedeBanner memory={memory} />

      <footer className="memory-card__foot">
        <div className="memory-card__meta">
          {memory.source ? (
            <span className="memory-card__tag">source: {memory.source}</span>
          ) : null}
          {searchMode && memory.matched_by && memory.matched_by.length > 0 ? (
            <span className="memory-card__tag">
              matched by {memory.matched_by.join(" + ")}
            </span>
          ) : null}
          {searchMode && typeof memory.score === "number" ? (
            <span
              className="memory-card__score"
              title="Fused text and vector rank score returned by search"
            >
              fused {memory.score.toFixed(4)}
            </span>
          ) : null}
        </div>
        <div className="memory-card__meta">
          {memory.created_at ? <span>pressed {formatDate(memory.created_at)}</span> : null}
          <Link className="memory-card__read" to={href}>
            Read record
            <Icon name="arrow-right" size={13} />
          </Link>
        </div>
      </footer>
    </article>
  );
}

function VaultTelemetry({
  searchMode,
  loading,
  visibleCount,
  loadedCount,
  total,
  searchStats,
  searchElapsed,
  filter,
  onFilterChange,
}: {
  readonly searchMode: boolean;
  readonly loading: boolean;
  readonly visibleCount: number;
  readonly loadedCount: number;
  readonly total: number;
  readonly searchStats?: {
    readonly text_candidates: number;
    readonly vector_candidates: number;
    readonly merged: number;
  };
  readonly searchElapsed?: number;
  readonly filter: StatusFilter;
  readonly onFilterChange: (value: StatusFilter) => void;
}) {
  let countLabel = `${formatNumber(visibleCount)} shown · ${formatNumber(loadedCount)} loaded · ${formatNumber(total)} total`;
  if (loading) {
    countLabel = searchMode ? "Searching memories…" : "Reading memories…";
  } else if (searchMode) {
    countLabel = `${formatNumber(visibleCount)} of ${formatNumber(loadedCount)} memory matches`;
  }

  return (
    <div className="memory-telemetry">
      <div className="memory-telemetry__group">
        <span className="memory-chip">
          <span
            className={["memory-chip__dot", searchMode ? "memory-chip__dot--seal" : null]
              .filter(Boolean)
              .join(" ")}
            aria-hidden="true"
          />
          {searchMode ? "Text + vector search" : "Newest occurrence first"}
        </span>
        <span className="memory-telemetry__count" aria-live="polite">
          {countLabel}
        </span>
        {searchMode && searchStats ? (
          <span className="memory-telemetry__diagnostics">
            <span title="Selected text candidates across all result kinds">
              text <strong>{formatNumber(searchStats.text_candidates)}</strong>
            </span>
            <span title="Selected vector candidates across all result kinds">
              vector <strong>{formatNumber(searchStats.vector_candidates)}</strong>
            </span>
            <span title="Deduplicated union of text and vector candidates">
              merged <strong>{formatNumber(searchStats.merged)}</strong>
            </span>
            {typeof searchElapsed === "number" ? (
              <span title="Server search duration">
                <strong>{formatNumber(searchElapsed)}</strong> ms
              </span>
            ) : null}
          </span>
        ) : null}
      </div>
      <MemoryStatusFilter value={filter} onChange={onFilterChange} />
    </div>
  );
}

interface SearchResultsProps {
  readonly loading: boolean;
  readonly enabled: boolean;
  readonly isError: boolean;
  readonly error: unknown;
  readonly query: string;
  readonly matches: readonly MemoryCardModel[];
  readonly filtered: readonly MemoryCardModel[];
  readonly filter: StatusFilter;
  readonly onRetry: () => void;
  readonly onClearSearch: () => void;
  readonly onShowAll: () => void;
}

function SearchResults({
  loading,
  enabled,
  isError,
  error,
  query,
  matches,
  filtered,
  filter,
  onRetry,
  onClearSearch,
  onShowAll,
}: SearchResultsProps) {
  if (loading) {
    return <MemorySkeleton label="Searching the vault" count={3} />;
  }
  if (enabled && isError) {
    return (
      <MemoryErrorState
        title="The vault search did not answer."
        description="The memory search request failed before any results were returned."
        error={error}
        onRetry={onRetry}
      />
    );
  }
  if (!enabled) {
    return null;
  }
  if (filtered.length > 0) {
    return (
      <div className="memory-list">
        {filtered.map((memory) => (
          <MemoryCard key={memory.memory_id} memory={memory} searchMode />
        ))}
      </div>
    );
  }
  if (matches.length === 0) {
    return (
      <MemoryEmptyState
        icon="search"
        eyebrow="No match"
        title="No crystal answers this phrase."
        description={`Search returned no memory matches for “${query}”. Try a broader phrase, or search the whole archive for related files and summaries.`}
        action={
          <>
            <Button variant="secondary" size="sm" onClick={onClearSearch}>
              Clear search
            </Button>
            <ButtonLink
              to={`/search?query=${encodeURIComponent(query)}`}
              variant="ghost"
              size="sm"
            >
              Search the whole archive
              <Icon name="arrow-right" size={14} />
            </ButtonLink>
          </>
        }
      />
    );
  }
  return (
    <MemoryEmptyState
      eyebrow="Filtered out"
      title={`No ${filterNoun(filter)} crystals in these matches.`}
      description="The search returned matches, but none have the selected status. Clear the status filter to see every match."
      action={
        <Button variant="secondary" size="sm" onClick={onShowAll}>
          Show all statuses
        </Button>
      }
    />
  );
}

interface BrowseResultsProps {
  readonly loading: boolean;
  readonly failed: boolean;
  readonly error: unknown;
  readonly total: number;
  readonly loadedCount: number;
  readonly filtered: readonly MemorySchema[];
  readonly filter: StatusFilter;
  readonly hasMore: boolean;
  readonly loadMoreLoading: boolean;
  readonly loadMoreError: unknown;
  readonly onRetry: () => void;
  readonly onLoadMore: () => void;
  readonly onRetryLoadMore: () => void;
  readonly onShowAll: () => void;
}

function BrowseResults({
  loading,
  failed,
  error,
  total,
  loadedCount,
  filtered,
  filter,
  hasMore,
  loadMoreLoading,
  loadMoreError,
  onRetry,
  onLoadMore,
  onRetryLoadMore,
  onShowAll,
}: BrowseResultsProps) {
  if (loading) {
    return <MemorySkeleton label="Reading the memory vault" count={3} />;
  }
  if (failed) {
    return (
      <MemoryErrorState
        title="The vault did not answer."
        description="The memory list request failed before any records were returned."
        error={error}
        onRetry={onRetry}
      />
    );
  }
  if (total === 0) {
    return (
      <MemoryEmptyState
        eyebrow="Empty vault"
        title="No memories have been pressed yet."
        description="A memory records a decision, an observation, or a change of mind. Press the first crystal to open the vault."
        action={
          <ButtonLink to="/memory/new" variant="ink" size="sm">
            <Icon name="plus" size={15} />
            Press the first memory
          </ButtonLink>
        }
      />
    );
  }

  let loadControl;
  if (loadMoreError) {
    loadControl = (
      <div className="memory-load__error" role="alert">
        <span>The next page of memories did not load.</span>
        <Button variant="secondary" size="sm" onClick={onRetryLoadMore}>
          Retry older records
        </Button>
      </div>
    );
  } else if (hasMore) {
    loadControl = (
      <>
        <p className="memory-load__note">
          {formatNumber(loadedCount)} of {formatNumber(total)} records loaded
        </p>
        <Button
          variant="secondary"
          size="md"
          disabled={loadMoreLoading}
          onClick={onLoadMore}
        >
          {loadMoreLoading ? "Loading older records…" : "Load older memories"}
        </Button>
      </>
    );
  } else {
    loadControl = (
      <p className="memory-end">
        End of the vault · {formatNumber(loadedCount)} memories read
      </p>
    );
  }

  return (
    <>
      {filtered.length === 0 ? (
        <MemoryEmptyState
          eyebrow="Filtered out"
          title={`No ${filterNoun(filter)} crystals in the loaded records.`}
          description={
            hasMore
              ? "The status filter only scans records already loaded. Load older records below, or clear the filter."
              : "Every loaded record has a different status. Clear the filter to see the full vault."
          }
          action={
            <Button variant="secondary" size="sm" onClick={onShowAll}>
              Show all statuses
            </Button>
          }
        />
      ) : (
        <div className="memory-list">
          {filtered.map((memory) => (
            <MemoryCard key={memory.memory_id} memory={memory} />
          ))}
        </div>
      )}
      <div className="memory-load" aria-busy={loadMoreLoading}>
        {loadControl}
      </div>
    </>
  );
}

/** The vault index at `/memory`: browse, search, filter, and load older pages. */
export function MemoryVault() {
  const searchInputId = useId();
  const [searchDraft, setSearchDraft] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [requestedPages, setRequestedPages] = useState(1);

  const debouncedDraft = useDebouncedValue(searchDraft, SEARCH_DEBOUNCE_MS);
  const isSearchMode = searchDraft.trim().length > 0;
  const searchQuery = isSearchMode ? debouncedDraft.trim() : "";
  const searchEnabled = searchQuery.length > 0;

  const search = useSearchKnowledge(
    {
      query: searchQuery,
      result_number: SEARCH_RESULT_LIMIT,
      include_history: true,
    },
    { query: { enabled: searchEnabled } },
  );

  const firstPage = useListMemories(
    { limit: PAGE_SIZE, offset: 0 },
    { query: { enabled: !isSearchMode } },
  );

  // The first page uses the generated hook; additional pages reuse its query
  // options so load-more appends without a state-syncing effect.
  const extraPages = useQueries({
    queries: Array.from({ length: Math.max(0, requestedPages - 1) }, (_, index) => {
      const pageIndex = index + 1;
      return {
        ...getListMemoriesQueryOptions({
          limit: PAGE_SIZE,
          offset: pageIndex * PAGE_SIZE,
        }),
        enabled: !isSearchMode,
      };
    }),
  });

  const stats = useGetStats();

  const loadedRows = [
    ...(firstPage.data?.resources ?? []),
    ...extraPages.flatMap((page) => page.data?.resources ?? []),
  ];
  const total = firstPage.data?.total_results ?? 0;
  const loadedCount = loadedRows.length;
  const lastExtraPage = extraPages.at(-1);
  const reachedEmptyPage =
    lastExtraPage?.data !== undefined && lastExtraPage.data.resources.length === 0;
  const hasMore = loadedCount < total && !reachedEmptyPage;
  const loadMoreError =
    lastExtraPage?.isError && !lastExtraPage.isFetching ? lastExtraPage.error : null;
  const loadMoreLoading = extraPages.some((page) => page.isFetching);
  const listLoading =
    !isSearchMode &&
    loadedCount === 0 &&
    (firstPage.isPending || (firstPage.isFetching && firstPage.data === undefined));
  const listFailed =
    !isSearchMode &&
    firstPage.data === undefined &&
    firstPage.isError &&
    !firstPage.isFetching;

  // The list endpoint has no status parameter, so filtering is scoped to
  // loaded pages and disclosed in the telemetry strip.
  const filteredRows = loadedRows.filter((memory) => matchesStatus(memory, statusFilter));

  const searchMatches = useMemo<MemoryCardModel[]>(() => {
    const best = new Map<number, MemoryCardModel>();
    for (const result of search.data?.memory_results ?? []) {
      const card: MemoryCardModel = {
        memory_id: result.memory_id,
        content: result.content,
        status: result.status === "deprecated" ? "deprecated" : "active",
        update_time: result.update_time,
        score: result.score,
        matched_by: result.matched_by,
      };
      const current = best.get(card.memory_id);
      if (!current || (card.score ?? 0) > (current.score ?? 0)) {
        best.set(card.memory_id, card);
      }
    }
    return [...best.values()];
  }, [search.data]);

  const filteredSearchMatches = searchMatches.filter((memory) =>
    matchesStatus(memory, statusFilter),
  );

  const searchLoading =
    isSearchMode &&
    (!searchEnabled ||
      search.isPending ||
      (search.isFetching && search.data === undefined));

  const activeCount = stats.data?.active_memory_count;
  const archiveCount = stats.data?.memory_count ?? (total > 0 ? total : undefined);
  const supersededCount =
    activeCount !== undefined && archiveCount !== undefined
      ? Math.max(0, archiveCount - activeCount)
      : undefined;

  const loadingNow = isSearchMode ? searchLoading : listLoading;
  const filterNote = buildFilterNote(
    statusFilter,
    isSearchMode,
    searchMatches.length,
    loadedCount,
    hasMore,
    loadingNow,
  );

  const searchNote = buildSearchNote(isSearchMode, searchEnabled);

  const handleLoadMore = () => {
    setRequestedPages((count) => count + 1);
  };

  const handleClearSearch = () => {
    setSearchDraft("");
  };

  return (
    <div className="content-container memory-page memory-vault">
      <PageHeader
        eyebrow="Memory · vault"
        title="Memory Vault"
        description="Every pressed memory, newest occurrence first. Active crystals stay in search and the timeline; superseded crystals remain readable with their lineage."
        meta={
          <span className="memory-masthead__counts">
            <span>
              <strong>{activeCount !== undefined ? formatNumber(activeCount) : "—"}</strong> active
            </span>
            <span className="memory-masthead__sep" aria-hidden="true">
              ·
            </span>
            <span>
              <strong>{supersededCount !== undefined ? formatNumber(supersededCount) : "—"}</strong>{" "}
              superseded
            </span>
          </span>
        }
        actions={
          <ButtonLink to="/memory/new" variant="primary" size="md">
            <Icon name="plus" size={15} />
            Press memory
          </ButtonLink>
        }
      />

      <div className="memory-vault__tools">
        <form
          className="memory-search"
          role="search"
          onSubmit={(event) => event.preventDefault()}
        >
          <span className="memory-search__icon" aria-hidden="true">
            <Icon name="search" size={20} />
          </span>
          <label className="visually-hidden" htmlFor={searchInputId}>
            Search memories
          </label>
          <input
            id={searchInputId}
            className="memory-search__input"
            type="search"
            value={searchDraft}
            maxLength={SEARCH_INPUT_MAX}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search memories by phrase or keyword…"
            autoComplete="off"
            spellCheck={false}
          />
          {searchDraft.length > 0 ? (
            <button
              type="button"
              className="memory-search__clear"
              onClick={handleClearSearch}
              aria-label="Clear memory search"
            >
              <Icon name="close" size={13} />
            </button>
          ) : null}
        </form>

        <VaultTelemetry
          searchMode={isSearchMode}
          loading={isSearchMode ? searchLoading : listLoading}
          visibleCount={isSearchMode ? filteredSearchMatches.length : filteredRows.length}
          loadedCount={isSearchMode ? searchMatches.length : loadedCount}
          total={isSearchMode ? searchMatches.length : total}
          searchStats={search.data?.stats}
          searchElapsed={search.data?.elapsed_ms}
          filter={statusFilter}
          onFilterChange={setStatusFilter}
        />
        {filterNote ? <p className="memory-filter-note">{filterNote}</p> : null}
        {searchNote ? <p className="memory-filter-note">{searchNote}</p> : null}
      </div>

      {isSearchMode ? (
        <SearchResults
          loading={searchLoading}
          enabled={searchEnabled}
          isError={search.isError}
          error={search.error}
          query={searchQuery}
          matches={searchMatches}
          filtered={filteredSearchMatches}
          filter={statusFilter}
          onRetry={() => {
            void search.refetch();
          }}
          onClearSearch={handleClearSearch}
          onShowAll={() => setStatusFilter("all")}
        />
      ) : (
        <BrowseResults
          loading={listLoading}
          failed={listFailed}
          error={firstPage.error}
          total={total}
          loadedCount={loadedCount}
          filtered={filteredRows}
          filter={statusFilter}
          hasMore={hasMore}
          loadMoreLoading={loadMoreLoading}
          loadMoreError={loadMoreError}
          onRetry={() => {
            void firstPage.refetch();
          }}
          onLoadMore={handleLoadMore}
          onRetryLoadMore={() => {
            if (lastExtraPage) {
              void lastExtraPage.refetch();
            }
          }}
          onShowAll={() => setStatusFilter("all")}
        />
      )}
    </div>
  );
}
