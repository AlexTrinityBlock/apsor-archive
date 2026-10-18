import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Badge } from "../component/Badge";
import { PageHeader } from "../component/PageHeader";
import {
  getSearchKnowledgeUrl,
  useSearchKnowledge,
} from "../generated-apis-types/search/search";
import { useDebouncedValue } from "../hook/useDebouncedValue";
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
  buildSearchParams,
  parseResultNumber,
} from "./component/url";
import "./search.css";

const INPUT_DEBOUNCE_MS = 350;

/**
 * Hybrid search across files, memories, and summaries.
 *
 * The URL is the single source of truth for query, N, and history. Typing is
 * debounced into a replace navigation; explicit submits and control changes
 * push a new history entry so back and forward remain useful.
 */
export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlQuery = searchParams.get("query") ?? "";
  const query = urlQuery.trim();
  const resultNumber = parseResultNumber(searchParams.get("result_number"));
  const includeHistory = searchParams.get("include_history") === "true";

  const [draft, setDraft] = useState(urlQuery);
  const debouncedDraft = useDebouncedValue(draft, INPUT_DEBOUNCE_MS);
  const lastUrlQuery = useRef(urlQuery);

  const search = useSearchKnowledge(
    {
      query,
      result_number: resultNumber,
      include_history: includeHistory,
    },
    { query: { enabled: Boolean(query) } },
  );

  useEffect(() => {
    if (lastUrlQuery.current !== urlQuery) {
      lastUrlQuery.current = urlQuery;
      setDraft(urlQuery);
      return;
    }
    if (debouncedDraft !== draft) {
      return;
    }
    const nextQuery = debouncedDraft.trim();
    if (nextQuery === urlQuery) {
      return;
    }
    setSearchParams(buildSearchParams(nextQuery, resultNumber, includeHistory), {
      replace: true,
    });
  }, [debouncedDraft, draft, includeHistory, resultNumber, setSearchParams, urlQuery]);

  const handleSubmit = (value: string) => {
    const nextQuery = value.trim();
    setDraft(nextQuery);
    if (nextQuery === urlQuery) {
      return;
    }
    setSearchParams(buildSearchParams(nextQuery, resultNumber, includeHistory));
  };

  const handleResultNumberChange = (value: number) => {
    const nextResultNumber = Math.min(10, Math.max(1, value));
    setSearchParams(buildSearchParams(draft, nextResultNumber, includeHistory));
  };

  const handleHistoryChange = (value: boolean) => {
    setSearchParams(buildSearchParams(draft, resultNumber, value));
  };

  const handleClear = () => {
    setDraft("");
    setSearchParams(buildSearchParams("", resultNumber, includeHistory));
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

  return (
    <div className="page search-page">
      <PageHeader
        eyebrow="Search · hybrid retrieval"
        title="Search the grain."
        description="One query, two lanes. BM25 and vector candidates are fused with reciprocal rank fusion, then capped per source kind so files, memories, and summaries each get a fair hearing."
        meta={<span>Per-kind top-N · RRF · dedup</span>}
        actions={<Badge tone="moss">BM25 + vector</Badge>}
      />

      <div className="reveal reveal-2">
        <SearchControls
          query={draft}
          onQueryChange={setDraft}
          onSubmit={handleSubmit}
          resultNumber={resultNumber}
          onResultNumberChange={handleResultNumberChange}
          includeHistory={includeHistory}
          onIncludeHistoryChange={handleHistoryChange}
        />
      </div>

      {!query ? <SearchWelcome /> : null}

      {query && search.isPending ? <SearchLoading /> : null}

      {query && !search.isPending && search.error ? (
        <SearchError
          error={search.error}
          endpoint={endpoint}
          onRetry={() => {
            void search.refetch();
          }}
        />
      ) : null}

      {query && !search.isPending && !search.error && data && totalResults === 0 ? (
        <SearchNoResults
          query={data.query}
          includeHistory={includeHistory}
          onIncludeHistory={() => handleHistoryChange(true)}
          onClear={handleClear}
        />
      ) : null}

      {query && !search.isPending && !search.error && data && totalResults > 0 ? (
        <>
          <SearchStats
            stats={data.stats}
            elapsedMs={data.elapsed_ms}
            resultNumber={data.result_number}
          />

          <section
            className="search-results reveal reveal-3"
            aria-label="Search results"
            aria-busy={search.isFetching}
          >
            <header className="search-results__head">
              <div>
                <p className="eyebrow">Retrieved grain</p>
                <h2>
                  {totalResults} {totalResults === 1 ? "passage" : "passages"} for
                  this query.
                </h2>
              </div>
              <div className="search-results__meta">
                <span className="search-results__query">
                  <span>Query</span>
                  <code>{data.query}</code>
                </span>
                {search.isFetching ? (
                  <span className="search-results__refining">Refining…</span>
                ) : null}
              </div>
            </header>

            <SearchResultGroup
              index="01"
              eyebrow="Source kind · file"
              title="Files"
              accent="moss"
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
              eyebrow="Source kind · memory"
              title="Memories"
              accent="vermilion"
              count={data.memory_results.length}
              emptyLabel="No memory matched this query."
            >
              {data.memory_results.map((result, index) => (
                <MemoryResultCard
                  key={`${result.memory_id}-${index}`}
                  result={result}
                  query={data.query}
                  rank={index + 1}
                />
              ))}
            </SearchResultGroup>

            <SearchResultGroup
              index="03"
              eyebrow="Source kind · summary"
              title="Summaries"
              accent="ochre"
              count={data.summary_results.length}
              emptyLabel="No summary matched this query."
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
        </>
      ) : null}
    </div>
  );
}
