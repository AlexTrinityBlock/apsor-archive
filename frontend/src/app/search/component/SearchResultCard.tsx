import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type {
  FileSearchResultSchema,
  MemorySearchResultSchema,
  SummarySearchResultSchema,
} from "../../generated-apis-types/schemas";
import { formatDate, formatDateTime, formatRelative } from "../../../lib/format";
import { highlightTerms, snippetAround } from "../../../lib/highlight";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";

const SNIPPET_LIMIT = 380;

type MatchSource = "text" | "vector";

interface CardProps<T> {
  readonly result: T;
  readonly query: string;
  readonly rank: number;
}

function rankLabel(rank: number): string {
  return String(rank).padStart(2, "0");
}

function libraryHref(fileId: number, chunk: number): string {
  const params = new URLSearchParams({
    file: String(fileId),
    chunk: String(chunk),
  });
  return `/library?${params.toString()}`;
}

function MatchedByBadges({ matchedBy }: { readonly matchedBy: readonly MatchSource[] }) {
  if (matchedBy.length === 0) {
    return null;
  }
  return (
    <span className="search-result__badges">
      {matchedBy.map((source) => (
        <Badge key={source} tone={source === "text" ? "moss" : "ochre"}>
          {source.toUpperCase()}
        </Badge>
      ))}
    </span>
  );
}

function SourceTime({ value }: { readonly value: string }) {
  return (
    <span className="search-result__time">
      <span>Updated</span>
      <time dateTime={value}>{formatDateTime(value)}</time>
      <span>({formatRelative(value)})</span>
    </span>
  );
}

function Score({ value }: { readonly value: number }) {
  return (
    <span className="search-result__score">
      <span className="eyebrow">Score</span>
      <strong>{value.toFixed(6)}</strong>
    </span>
  );
}

function CardFrame({
  rank,
  rankTone,
  children,
}: {
  readonly rank: number;
  readonly rankTone: "file" | "memory" | "summary";
  readonly children: ReactNode;
}) {
  return (
    <article className={`search-result search-result--${rankTone}`}>
      <span className="search-result__rank" aria-hidden="true">
        {rankLabel(rank)}
      </span>
      <div className="search-result__body">{children}</div>
    </article>
  );
}

/** A file chunk result with a pointer back into the library reader. */
export function FileResultCard({ result, query, rank }: CardProps<FileSearchResultSchema>) {
  const href = libraryHref(result.file_id, result.chunk);

  return (
    <CardFrame rank={rank} rankTone="file">
      <div className="search-result__top">
        <div className="search-result__source">
          <span className="search-result__kind" aria-hidden="true">
            <Icon name="file" size={17} />
          </span>
          <div className="search-result__identity">
            <Link className="search-result__label" to={href}>
              {result.raw_file_path}
            </Link>
            <span className="search-result__meta">
              <span>Chunk {result.chunk}</span>
              <span aria-hidden="true">·</span>
              <SourceTime value={result.update_time} />
              {!result.is_current ? <Badge tone="ochre">history</Badge> : null}
            </span>
          </div>
        </div>
        <Score value={result.score} />
      </div>

      <p className="search-result__snippet">
        {highlightTerms(snippetAround(result.content, query, SNIPPET_LIMIT), query)}
      </p>

      <footer className="search-result__foot">
        <MatchedByBadges matchedBy={result.matched_by} />
        <Link className="search-result__action" to={href}>
          Open in library
          <Icon name="arrow-up-right" size={14} />
        </Link>
      </footer>
    </CardFrame>
  );
}

/** A memory result that keeps its status visible and traces back to the ledger. */
export function MemoryResultCard({ result, query, rank }: CardProps<MemorySearchResultSchema>) {
  const href = `/memory/${result.memory_id}`;

  return (
    <CardFrame rank={rank} rankTone="memory">
      <div className="search-result__top">
        <div className="search-result__source">
          <span className="search-result__kind" aria-hidden="true">
            <Icon name="memory" size={17} />
          </span>
          <div className="search-result__identity">
            <Link className="search-result__label" to={href}>
              Memory #{result.memory_id}
            </Link>
            <span className="search-result__meta">
              <Badge tone={result.status === "active" ? "moss" : "ochre"} dot>
                {result.status}
              </Badge>
              <span aria-hidden="true">·</span>
              <SourceTime value={result.update_time} />
            </span>
          </div>
        </div>
        <Score value={result.score} />
      </div>

      <p className="search-result__snippet">
        {highlightTerms(snippetAround(result.content, query, SNIPPET_LIMIT), query)}
      </p>

      <footer className="search-result__foot">
        <MatchedByBadges matchedBy={result.matched_by} />
        <Link className="search-result__action" to={href}>
          Trace memory
          <Icon name="arrow-up-right" size={14} />
        </Link>
      </footer>
    </CardFrame>
  );
}

/** A memory-summary chunk with its period and themes kept in view. */
export function SummaryResultCard({
  result,
  query,
  rank,
}: CardProps<SummarySearchResultSchema>) {
  return (
    <CardFrame rank={rank} rankTone="summary">
      <div className="search-result__top">
        <div className="search-result__source">
          <span className="search-result__kind" aria-hidden="true">
            <Icon name="layers" size={17} />
          </span>
          <div className="search-result__identity">
            <span className="search-result__label">Summary #{result.memory_summary_id}</span>
            <span className="search-result__meta">
              <span>
                Period {formatDate(result.period_start)} – {formatDate(result.period_end)}
              </span>
              <span aria-hidden="true">·</span>
              <SourceTime value={result.update_time} />
            </span>
          </div>
        </div>
        <Score value={result.score} />
      </div>

      <p className="search-result__snippet">
        {highlightTerms(snippetAround(result.content, query, SNIPPET_LIMIT), query)}
      </p>

      {result.themes.length > 0 ? (
        <p className="search-result__themes" aria-label="Summary themes">
          {result.themes.map((theme) => (
            <span className="search-result__theme" key={theme}>
              #{theme}
            </span>
          ))}
        </p>
      ) : null}

      <footer className="search-result__foot">
        <MatchedByBadges matchedBy={result.matched_by} />
        <span className="search-result__source-tag">Memory summary</span>
      </footer>
    </CardFrame>
  );
}
