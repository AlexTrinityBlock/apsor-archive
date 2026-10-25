import { useId, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button, ButtonLink } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
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
import {
  useI18n,
  type Translate,
  type TranslationKey,
} from "../../i18n";

import {
  MemoryDeprecateDialog,
  MemoryEditDialog,
  type MemoryActionTarget,
} from "./MemoryActionDialogs";
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

const STATUS_FILTERS: ReadonlyArray<{
  readonly value: StatusFilter;
  readonly labelKey: TranslationKey;
}> = [
  { value: "all", labelKey: "memory.status.filterAll" },
  { value: "active", labelKey: "memory.status.filterActive" },
  { value: "deprecated", labelKey: "memory.status.filterDeprecated" },
];

interface MemoryCardModel {
  readonly memory_id: number;
  readonly title?: string;
  readonly content: string;
  readonly status: "active" | "deprecated";
  readonly update_time: string;
  readonly source?: MemorySchema["source"];
  readonly created_at?: string;
  readonly supersedes_ids?: readonly number[];
  readonly superseded_by_id?: number | null;
  readonly deprecated_reason?: string | null;
  readonly score?: number;
  readonly matched_by?: readonly string[];
}

function matchesStatus(memory: MemoryCardModel, filter: StatusFilter): boolean {
  return filter === "all" || memory.status === filter;
}

function filterNounKey(filter: StatusFilter): TranslationKey {
  if (filter === "active") {
    return "memory.status.nounActive";
  }
  if (filter === "deprecated") {
    return "memory.status.nounDeprecated";
  }
  return "memory.status.nounMatching";
}

function buildFilterNote(
  filter: StatusFilter,
  searchMode: boolean,
  searchMatchCount: number,
  loadedCount: number,
  hasMore: boolean,
  loading: boolean,
  t: Translate,
  formatNumber: (value: number) => string,
): string | null {
  if (loading || filter === "all") {
    return null;
  }
  if (searchMode) {
    return t("memory.vault.filterNoteSearch", {
      count: formatNumber(searchMatchCount),
    });
  }
  return t(
    hasMore
      ? "memory.vault.filterNoteLoadedMore"
      : "memory.vault.filterNoteLoaded",
    { count: formatNumber(loadedCount) },
  );
}

function buildSearchNote(
  searchMode: boolean,
  searchEnabled: boolean,
  t: Translate,
): string | null {
  if (!searchMode || !searchEnabled) {
    return null;
  }
  return t("memory.vault.searchNote", { limit: SEARCH_RESULT_LIMIT });
}

function MemoryStatusFilter({
  value,
  onChange,
}: {
  readonly value: StatusFilter;
  readonly onChange: (value: StatusFilter) => void;
}) {
  const { t } = useI18n();

  return (
    <div
      className="tabs tabs--light memory-filter"
      role="group"
      aria-label={t("memory.status.filterAria")}
    >
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
          {t(option.labelKey)}
        </button>
      ))}
    </div>
  );
}

function SupersedeBanner({ memory }: { readonly memory: MemoryCardModel }) {
  const { t } = useI18n();

  if (memory.status === "deprecated") {
    return (
      <div className="memory-card__banner is-deprecated">
        <span>
          {memory.superseded_by_id !== null && memory.superseded_by_id !== undefined ? (
            <>
              {t("memory.card.supersededByPrefix")}
              <Link to={`/memory/${memory.superseded_by_id}`}>
                {t("memory.common.crystal", { id: memory.superseded_by_id })}
              </Link>
              {t("memory.card.supersededBySuffix")}
            </>
          ) : (
            t("memory.card.deprecatedDirectly")
          )}
        </span>
        {memory.deprecated_reason ? (
          <span className="memory-card__banner-reason">
            {t("memory.common.reason", { reason: memory.deprecated_reason })}
          </span>
        ) : null}
      </div>
    );
  }
  if (memory.supersedes_ids && memory.supersedes_ids.length > 0) {
    return (
      <div className="memory-card__banner">
        <span>
          {t("memory.card.replacesPrefix")}
          {memory.supersedes_ids.map((id, index) => (
            <span key={id}>
              {index > 0 ? ", " : null}
              <Link to={`/memory/${id}`}>
                {t("memory.common.crystal", { id })}
              </Link>
            </span>
          ))}
          {t("memory.card.replacesSuffix")}
        </span>
      </div>
    );
  }
  return null;
}

function MemoryCard({
  memory,
  searchMode = false,
  onEdit,
  onDeprecate,
}: {
  readonly memory: MemoryCardModel;
  readonly searchMode?: boolean;
  readonly onEdit: (memory: MemoryCardModel) => void;
  readonly onDeprecate: (memory: MemoryCardModel) => void;
}) {
  const { t, formatDate, formatDateTime } = useI18n();
  const preview = splitMemoryPreview(
    memory.content,
    t("memory.common.untitledMemory"),
  );
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
            {t("memory.common.crystal", { id: memory.memory_id })}
          </Link>
          <MemoryStatus status={memory.status} />
        </div>
        <span className="memory-card__epoch">
          {t("memory.common.occurred")}{" "}
          <time dateTime={memory.update_time}>{formatDateTime(memory.update_time)}</time>
        </span>
      </header>

      <h2 className="memory-card__thesis">
        <Link to={href}>{memory.title || preview.thesis}</Link>
      </h2>
      {preview.body ? <p className="memory-card__body">{preview.body}</p> : null}

      <SupersedeBanner memory={memory} />

      <footer className="memory-card__foot">
        <div className="memory-card__meta">
          {memory.source ? (
            <span className="memory-card__tag">
              {t("memory.common.sourceValue", { source: memory.source })}
            </span>
          ) : null}
          {searchMode && memory.matched_by && memory.matched_by.length > 0 ? (
            <span className="memory-card__tag">
              {t("memory.card.matchedBy", {
                by: memory.matched_by.join(" + "),
              })}
            </span>
          ) : null}
          {searchMode && typeof memory.score === "number" ? (
            <span
              className="memory-card__score"
              title={t("memory.card.fusedScoreTitle")}
            >
              {t("memory.card.fusedScore", {
                score: memory.score.toFixed(4),
              })}
            </span>
          ) : null}
        </div>
        <div className="memory-card__meta">
          {memory.created_at ? (
            <span>
              {t("memory.card.pressedAt", {
                date: formatDate(memory.created_at),
              })}
            </span>
          ) : null}
          <CopyButton
            value={memory.content}
            label={t("memory.common.copyMemory")}
            iconOnly
            title={t("memory.common.copyMemoryTitle")}
          />
          <button
            type="button"
            className="memory-card__action"
            onClick={() => onEdit(memory)}
          >
            {t("memory.card.edit")}
          </button>
          {memory.status === "active" ? (
            <button
              type="button"
              className="memory-card__action is-danger"
              onClick={() => onDeprecate(memory)}
            >
              {t("memory.card.deprecate")}
            </button>
          ) : null}
          <Link className="memory-card__read" to={href}>
            {t("memory.card.readRecord")}
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
  const { t, formatNumber } = useI18n();
  let countLabel = t("memory.vault.shownLoadedTotal", {
    visible: formatNumber(visibleCount),
    loaded: formatNumber(loadedCount),
    total: formatNumber(total),
  });
  if (loading) {
    countLabel = searchMode
      ? t("memory.vault.searchingMemories")
      : t("memory.vault.readingMemories");
  } else if (searchMode) {
    countLabel = t("memory.vault.searchMatchesCount", {
      visible: formatNumber(visibleCount),
      loaded: formatNumber(loadedCount),
    });
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
          {searchMode
            ? t("memory.vault.searchModeTextVector")
            : t("memory.vault.searchModeNewest")}
        </span>
        <span className="memory-telemetry__count" aria-live="polite">
          {countLabel}
        </span>
        {searchMode && searchStats ? (
          <span className="memory-telemetry__diagnostics">
            <span title={t("memory.vault.textCandidatesTitle")}>
              {t("memory.vault.diagnosticText")}{" "}
              <strong>{formatNumber(searchStats.text_candidates)}</strong>
            </span>
            <span title={t("memory.vault.vectorCandidatesTitle")}>
              {t("memory.vault.diagnosticVector")}{" "}
              <strong>{formatNumber(searchStats.vector_candidates)}</strong>
            </span>
            <span title={t("memory.vault.mergedCandidatesTitle")}>
              {t("memory.vault.diagnosticMerged")}{" "}
              <strong>{formatNumber(searchStats.merged)}</strong>
            </span>
            {typeof searchElapsed === "number" ? (
              <span title={t("memory.vault.serverDurationTitle")}>
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
  readonly onEdit: (memory: MemoryCardModel) => void;
  readonly onDeprecate: (memory: MemoryCardModel) => void;
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
  onEdit,
  onDeprecate,
}: SearchResultsProps) {
  const { t } = useI18n();

  if (loading) {
    return <MemorySkeleton label={t("memory.vault.searchSkeleton")} count={3} />;
  }
  if (enabled && isError) {
    return (
      <MemoryErrorState
        title={t("memory.vault.searchErrorTitle")}
        description={t("memory.vault.searchErrorDescription")}
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
          <MemoryCard
            key={memory.memory_id}
            memory={memory}
            searchMode
            onEdit={onEdit}
            onDeprecate={onDeprecate}
          />
        ))}
      </div>
    );
  }
  if (matches.length === 0) {
    return (
      <MemoryEmptyState
        icon="search"
        eyebrow={t("memory.vault.noMatchEyebrow")}
        title={t("memory.vault.noMatchTitle")}
        description={t("memory.vault.noMatchDescription", { query })}
        action={
          <>
            <Button variant="secondary" size="sm" onClick={onClearSearch}>
              {t("memory.vault.clearSearch")}
            </Button>
            <ButtonLink
              to={`/search?query=${encodeURIComponent(query)}`}
              variant="ghost"
              size="sm"
            >
              {t("memory.vault.searchWholeArchive")}
              <Icon name="arrow-right" size={14} />
            </ButtonLink>
          </>
        }
      />
    );
  }
  return (
    <MemoryEmptyState
      eyebrow={t("memory.vault.filteredEyebrow")}
      title={t("memory.vault.filteredSearchTitle", {
        status: t(filterNounKey(filter)),
      })}
      description={t("memory.vault.filteredSearchDescription")}
      action={
        <Button variant="secondary" size="sm" onClick={onShowAll}>
          {t("memory.vault.showAllStatuses")}
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
  readonly onEdit: (memory: MemoryCardModel) => void;
  readonly onDeprecate: (memory: MemoryCardModel) => void;
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
  onEdit,
  onDeprecate,
}: BrowseResultsProps) {
  const { t, formatNumber } = useI18n();

  if (loading) {
    return <MemorySkeleton label={t("memory.vault.browseSkeleton")} count={3} />;
  }
  if (failed) {
    return (
      <MemoryErrorState
        title={t("memory.vault.browseErrorTitle")}
        description={t("memory.vault.browseErrorDescription")}
        error={error}
        onRetry={onRetry}
      />
    );
  }
  if (total === 0) {
    return (
      <MemoryEmptyState
        eyebrow={t("memory.vault.emptyEyebrow")}
        title={t("memory.vault.emptyTitle")}
        description={t("memory.vault.emptyDescription")}
        action={
          <ButtonLink to="/memory/new" variant="ink" size="sm">
            <Icon name="plus" size={15} />
            {t("memory.vault.pressFirstMemory")}
          </ButtonLink>
        }
      />
    );
  }

  let loadControl;
  if (loadMoreError) {
    loadControl = (
      <div className="memory-load__error" role="alert">
        <span>{t("memory.vault.loadMoreError")}</span>
        <Button variant="secondary" size="sm" onClick={onRetryLoadMore}>
          {t("memory.vault.retryOlderRecords")}
        </Button>
      </div>
    );
  } else if (hasMore) {
    loadControl = (
      <>
        <p className="memory-load__note">
          {t("memory.vault.loadedOfTotal", {
            loaded: formatNumber(loadedCount),
            total: formatNumber(total),
          })}
        </p>
        <Button
          variant="secondary"
          size="md"
          disabled={loadMoreLoading}
          onClick={onLoadMore}
        >
          {loadMoreLoading
            ? t("memory.vault.loadingOlder")
            : t("memory.vault.loadOlder")}
        </Button>
      </>
    );
  } else {
    loadControl = (
      <p className="memory-end">
        {t("memory.vault.endOfVault", {
          count: formatNumber(loadedCount),
        })}
      </p>
    );
  }

  return (
    <>
      {filtered.length === 0 ? (
        <MemoryEmptyState
          eyebrow={t("memory.vault.filteredEyebrow")}
          title={t("memory.vault.filteredBrowseTitle", {
            status: t(filterNounKey(filter)),
          })}
          description={
            hasMore
              ? t("memory.vault.filteredBrowseMoreDescription")
              : t("memory.vault.filteredBrowseEndDescription")
          }
          action={
            <Button variant="secondary" size="sm" onClick={onShowAll}>
              {t("memory.vault.showAllStatuses")}
            </Button>
          }
        />
      ) : (
        <div className="memory-list">
          {filtered.map((memory) => (
            <MemoryCard
              key={memory.memory_id}
              memory={memory}
              onEdit={onEdit}
              onDeprecate={onDeprecate}
            />
          ))}
        </div>
      )}
      <div className="memory-load" aria-busy={loadMoreLoading}>
        {loadControl}
      </div>
    </>
  );
}

function VaultActionDialogs({
  editTarget,
  deprecateTarget,
  onCloseEdit,
  onCloseDeprecate,
}: {
  readonly editTarget: MemoryActionTarget | null;
  readonly deprecateTarget: MemoryActionTarget | null;
  readonly onCloseEdit: () => void;
  readonly onCloseDeprecate: () => void;
}) {
  return (
    <>
      {editTarget ? (
        <MemoryEditDialog memory={editTarget} onClose={onCloseEdit} />
      ) : null}
      {deprecateTarget ? (
        <MemoryDeprecateDialog
          memory={deprecateTarget}
          onClose={onCloseDeprecate}
        />
      ) : null}
    </>
  );
}

function toActionTarget(memory: MemoryCardModel): MemoryActionTarget {
  return {
    memory_id: memory.memory_id,
    title: memory.title ?? "",
    content: memory.content,
    status: memory.status,
  };
}

/** The vault index at `/memory`: browse, search, filter, and load older pages. */
export function MemoryVault() {
  const { t, formatNumber } = useI18n();
  const searchInputId = useId();
  const [searchDraft, setSearchDraft] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [requestedPages, setRequestedPages] = useState(1);
  const [editTarget, setEditTarget] = useState<MemoryActionTarget | null>(null);
  const [deprecateTarget, setDeprecateTarget] =
    useState<MemoryActionTarget | null>(null);

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
        title: result.title,
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
    t,
    formatNumber,
  );

  const searchNote = buildSearchNote(isSearchMode, searchEnabled, t);

  const handleLoadMore = () => {
    setRequestedPages((count) => count + 1);
  };

  const handleClearSearch = () => {
    setSearchDraft("");
  };

  const openEdit = (memory: MemoryCardModel) => {
    setEditTarget(toActionTarget(memory));
  };

  const openDeprecate = (memory: MemoryCardModel) => {
    setDeprecateTarget(toActionTarget(memory));
  };

  return (
    <div className="content-container memory-page memory-vault">
      <PageHeader
        eyebrow={t("memory.vault.eyebrow")}
        title={t("memory.vault.title")}
        description={t("memory.vault.description")}
        meta={
          <span className="memory-masthead__counts">
            <span>
              <strong>
                {activeCount !== undefined ? formatNumber(activeCount) : "—"}
              </strong>{" "}
              {t("memory.vault.activeLabel")}
            </span>
            <span className="memory-masthead__sep" aria-hidden="true">
              ·
            </span>
            <span>
              {supersededCount !== undefined
                ? formatNumber(supersededCount)
                : "—"}{" "}
              {t("memory.vault.deprecatedLabel")}
            </span>
          </span>
        }
        actions={
          <ButtonLink to="/memory/new" variant="primary" size="md">
            <Icon name="plus" size={15} />
            {t("memory.vault.pressMemory")}
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
            {t("memory.vault.searchLabel")}
          </label>
          <input
            id={searchInputId}
            className="memory-search__input"
            type="search"
            value={searchDraft}
            maxLength={SEARCH_INPUT_MAX}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder={t("memory.vault.searchPlaceholder")}
            autoComplete="off"
            spellCheck={false}
          />
          {searchDraft.length > 0 ? (
            <button
              type="button"
              className="memory-search__clear"
              onClick={handleClearSearch}
              aria-label={t("memory.vault.clearSearchAria")}
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
          onEdit={openEdit}
          onDeprecate={openDeprecate}
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
          onEdit={openEdit}
          onDeprecate={openDeprecate}
        />
      )}

      <VaultActionDialogs
        editTarget={editTarget}
        deprecateTarget={deprecateTarget}
        onCloseEdit={() => setEditTarget(null)}
        onCloseDeprecate={() => setDeprecateTarget(null)}
      />
    </div>
  );
}
