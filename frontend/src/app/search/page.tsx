import { useEffect, useRef, useState } from "react";
import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { truncate } from "../../lib/format";
import { Badge } from "../component/Badge";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { useToast } from "../component/Toast";
import {
  getListSavedQuestionsQueryKey,
  getSearchKnowledgeUrl,
  useCreateSavedQuestion,
  useSearchKnowledge,
} from "../generated-apis-types";
import { SearchControls } from "./component/SearchControls";
import {
  FileResultCard,
  MemoryResultCard,
  SummaryResultCard,
} from "./component/SearchResultCard";
import { SearchResultGroup } from "./component/SearchResultGroup";
import { SearchStats } from "./component/SearchStats";
import {
  SearchError,
  SearchLoading,
  SearchNoResults,
  SearchWelcome,
} from "./component/SearchStates";
import {
  clampResultNumber,
  parseResultNumber,
  withIncludeHistory,
  withQuery,
  withResultNumber,
} from "./component/url";
import "./search.css";

const INPUT_DEBOUNCE_MS = 350;

interface DraftEdit {
  readonly base: string;
  readonly value: string;
}

/**
 * Hybrid search across file chunks, memory crystals, and summaries.
 *
 * The URL is the single source of truth for query, result count, and history.
 * Typing is debounced into a replace navigation. Explicit submits, the history
 * switch, and clear push a new entry; the result-count slider replaces so a
 * drag does not flood the back stack.
 */
export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const searchInputRef = useRef<HTMLInputElement>(null);

  const urlQuery = searchParams.get("query") ?? "";
  const query = urlQuery.trim();
  const resultNumber = parseResultNumber(searchParams.get("result_number"));
  const includeHistory = searchParams.get("include_history") === "true";

  // The URL owns the committed query. An edit is only valid for the URL value
  // it started from, so external navigation discards the draft.
  const [draftEdit, setDraftEdit] = useState<DraftEdit | null>(null);
  const [lastUrlQuery, setLastUrlQuery] = useState(urlQuery);

  if (lastUrlQuery !== urlQuery) {
    setLastUrlQuery(urlQuery);
    setDraftEdit(null);
  }

  const draft =
    draftEdit !== null && draftEdit.base === urlQuery ? draftEdit.value : urlQuery;

  useEffect(() => {
    const nextQuery = draft.trim();
    if (nextQuery === urlQuery) {
      return;
    }
    const timer = window.setTimeout(() => {
      setSearchParams((previous) => withQuery(previous, nextQuery), {
        replace: true,
      });
    }, INPUT_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [draft, urlQuery, setSearchParams]);

  const search = useSearchKnowledge(
    {
      query,
      result_number: resultNumber,
      include_history: includeHistory,
    },
    {
      query: {
        enabled: query.length > 0,
        placeholderData: keepPreviousData,
      },
    },
  );

  const createQuestion = useCreateSavedQuestion({
    mutation: {
      onSuccess: async (saved) => {
        toast.success(`Saved “${truncate(saved.question, 72)}”.`);
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
      },
      onError: (error) => {
        toast.error(
          error instanceof Error && error.message.length > 0
            ? error.message
            : "The question could not be saved.",
        );
      },
    },
  });

  const commitQuery = (value: string, replace = false) => {
    const nextQuery = value.trim();
    setDraftEdit(null);
    if (nextQuery === urlQuery) {
      return;
    }
    setSearchParams((previous) => withQuery(previous, nextQuery), { replace });
  };

  const handleDraftChange = (value: string) => {
    setDraftEdit({ base: urlQuery, value });
  };

  const handleSubmit = (value: string) => {
    commitQuery(value);
  };

  const handleResultNumberChange = (value: number) => {
    const nextResultNumber = clampResultNumber(value);
    setSearchParams((previous) => withResultNumber(previous, nextResultNumber), {
      replace: true,
    });
  };

  const handleHistoryChange = (value: boolean) => {
    setSearchParams((previous) => withIncludeHistory(previous, value));
  };

  const handleClear = () => {
    setDraftEdit(null);
    setSearchParams((previous) => withQuery(previous, ""));
    searchInputRef.current?.focus();
  };

  const handleSaveQuestion = () => {
    const question = draft.trim();
    if (question.length === 0 || createQuestion.isPending) {
      return;
    }
    createQuestion.mutate({ data: { question } });
  };

  const endpoint = getSearchKnowledgeUrl({
    query,
    result_number: resultNumber,
    include_history: includeHistory,
  });

  const data = search.data;
  const totalResults = data
    ? data.file_results.length + data.memory_results.length + data.summary_results.length
    : 0;
  const searchSettling = query.length > 0 && search.isPending;

  return (
    <div className="content-container search-page">
      <PageHeader
        eyebrow="Search · Hybrid Retrieval Engine"
        title="Search the grain."
        description="One query, two lanes. BM25 lexical hits and dense vector candidates are fused with reciprocal rank fusion, then capped per source kind so files, memories, and summaries each receive a balanced hearing."
        meta={
          <span className="search-header__flags">
            <Badge tone="moss">BM25 + cosine fusion</Badge>
            <span className="shell-tag">RRF · k = 60</span>
          </span>
        }
      />

      <SearchControls
        draft={draft}
        onDraftChange={handleDraftChange}
        onSubmit={handleSubmit}
        onClear={handleClear}
        inputRef={searchInputRef}
        resultNumber={resultNumber}
        onResultNumberChange={handleResultNumberChange}
        includeHistory={includeHistory}
        onIncludeHistoryChange={handleHistoryChange}
        elapsedMs={query.length > 0 && data ? data.elapsed_ms : null}
        isFetching={query.length > 0 && search.isFetching}
        canClear={draft.length > 0 || query.length > 0}
        canSaveQuestion={draft.trim().length > 0}
        isSavingQuestion={createQuestion.isPending}
        onSaveQuestion={handleSaveQuestion}
      />

      {query.length === 0 ? <SearchWelcome /> : null}

      {searchSettling ? <SearchLoading /> : null}

      {query.length > 0 && !search.isPending && search.isError ? (
        <SearchError
          error={search.error}
          endpoint={endpoint}
          onRetry={() => {
            void search.refetch();
          }}
        />
      ) : null}

      {query.length > 0 && !search.isPending && !search.isError && data ? (
        <div className="search-output" aria-busy={search.isFetching}>
          <SearchStats stats={data.stats} elapsedMs={data.elapsed_ms} />

          {totalResults === 0 ? (
            <SearchNoResults
              query={data.query}
              includeHistory={includeHistory}
              isFetching={search.isFetching}
              onIncludeHistory={() => handleHistoryChange(true)}
              onClear={handleClear}
            />
          ) : (
            <section className="search-results" aria-label="Search results">
              <header className="search-results__head">
                <div>
                  <p className="eyebrow">Retrieved passages</p>
                  <h2 className="search-results__title">
                    {`${totalResults} ${totalResults === 1 ? "passage" : "passages"} for “${data.query}”`}
                  </h2>
                </div>
                <div className="search-results__meta">
                  <Badge tone="neutral">N = {data.result_number} per kind</Badge>
                  {search.isFetching ? (
                    <span className="search-results__busy">
                      <Loader size={12} label="Updating results" />
                      Updating…
                    </span>
                  ) : null}
                </div>
              </header>

              <SearchResultGroup
                index="01"
                title="File chunks"
                tone="files"
                count={data.file_results.length}
                emptyLabel="No file chunks matched this query."
              >
                {data.file_results.map((result, index) => (
                  <FileResultCard
                    key={result.chunk_id}
                    result={result}
                    query={data.query}
                    rank={index + 1}
                  />
                ))}
              </SearchResultGroup>

              <SearchResultGroup
                index="02"
                title="Memory crystals"
                tone="memories"
                count={data.memory_results.length}
                emptyLabel="No memory crystals matched this query."
              >
                {data.memory_results.map((result, index) => (
                  <MemoryResultCard
                    key={result.memory_id}
                    result={result}
                    query={data.query}
                    rank={index + 1}
                  />
                ))}
              </SearchResultGroup>

              <SearchResultGroup
                index="03"
                title="Summaries"
                tone="summaries"
                count={data.summary_results.length}
                emptyLabel="No summaries matched this query."
              >
                {data.summary_results.map((result, index) => (
                  <SummaryResultCard
                    key={result.memory_summary_id}
                    result={result}
                    query={data.query}
                    rank={index + 1}
                  />
                ))}
              </SearchResultGroup>
            </section>
          )}
        </div>
      ) : null}
    </div>
  );
}
