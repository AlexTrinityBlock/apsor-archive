import { useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { formatDate, formatDateTime } from "../../../lib/format";
import { highlightTerms, snippetAround } from "../../../lib/highlight";
import { Badge } from "../../component/Badge";
import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import type {
  FileSearchResultSchema,
  MemorySearchResultSchema,
  SummarySearchResultSchema,
} from "../../generated-apis-types/schemas";

const SNIPPET_LIMIT = 380;

type MatchSource = FileSearchResultSchema["matched_by"][number];
type ResultTone = "file" | "memory" | "summary";

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
    tab: "files",
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
    <span className="search-result__badges" aria-label="Matched by">
      {matchedBy.map((source) => (
        <Badge key={source} tone={source === "text" ? "moss" : "ochre"}>
          {source.toUpperCase()}
        </Badge>
      ))}
    </span>
  );
}

function FusedScore({ value }: { readonly value: number }) {
  return (
    <span
      className="search-result__score"
      title="Reciprocal-rank fusion score returned by the search API"
      aria-label={`Fused score ${value.toFixed(6)}`}
    >
      <span>Fused</span>
      <strong>{value.toFixed(6)}</strong>
    </span>
  );
}

function CardFrame({
  tone,
  rank,
  children,
}: {
  readonly tone: ResultTone;
  readonly rank: number;
  readonly children: ReactNode;
}) {
  return (
    <article className={`search-result search-result--${tone}`}>
      <span className="search-result__rank">
        <span className="visually-hidden">Rank </span>
        {rankLabel(rank)}
      </span>
      <div className="search-result__body">{children}</div>
    </article>
  );
}

/** A file chunk with a pointer into the Library preview modal. */
export function FileResultCard({ result, query, rank }: CardProps<FileSearchResultSchema>) {
  const href = libraryHref(result.file_id, result.chunk);

  return (
    <CardFrame tone="file" rank={rank}>
      <div className="search-result__top">
        <div className="search-result__identity">
          <span className="search-result__label">
            <Icon name="file" size={15} className="search-result__kind-icon" />
            <Link className="search-result__path" to={href}>
              {result.raw_file_path}
            </Link>
            <Badge>Chunk #{result.chunk}</Badge>
            {!result.is_current ? <Badge tone="ochre">history</Badge> : null}
          </span>
          <span className="search-result__meta">
            <span>
              Updated{" "}
              <time dateTime={result.update_time}>{formatDateTime(result.update_time)}</time>
            </span>
          </span>
        </div>
        <div className="search-result__side">
          <MatchedByBadges matchedBy={result.matched_by} />
          <FusedScore value={result.score} />
        </div>
      </div>

      <p className="search-result__snippet">
        {highlightTerms(snippetAround(result.content, query, SNIPPET_LIMIT), query)}
      </p>

      <div className="search-result__foot">
        <ButtonLink to={href} variant="secondary" size="sm">
          Open in library
          <Icon name="arrow-up-right" size={14} />
        </ButtonLink>
      </div>
    </CardFrame>
  );
}

/** A memory crystal with its status and a link to the memory reader. */
export function MemoryResultCard({ result, query, rank }: CardProps<MemorySearchResultSchema>) {
  const href = `/memory/${result.memory_id}`;

  return (
    <CardFrame tone="memory" rank={rank}>
      <div className="search-result__top">
        <div className="search-result__identity">
          <span className="search-result__label">
            <Icon name="memory" size={15} className="search-result__kind-icon" />
            <Link className="search-result__path" to={href}>
              Memory #{result.memory_id}
            </Link>
            <Badge tone={result.status === "active" ? "moss" : "ochre"} dot>
              {result.status}
            </Badge>
          </span>
          <span className="search-result__meta">
            <span>
              Recorded{" "}
              <time dateTime={result.update_time}>{formatDateTime(result.update_time)}</time>
            </span>
          </span>
        </div>
        <div className="search-result__side">
          <MatchedByBadges matchedBy={result.matched_by} />
          <FusedScore value={result.score} />
        </div>
      </div>

      <p className="search-result__snippet">
        {highlightTerms(snippetAround(result.content, query, SNIPPET_LIMIT), query)}
      </p>

      <div className="search-result__foot">
        <ButtonLink to={href} variant="secondary" size="sm">
          Trace memory
          <Icon name="arrow-right" size={14} />
        </ButtonLink>
      </div>
    </CardFrame>
  );
}

/** A summary that expands in place; it has no reader route. */
export function SummaryResultCard({
  result,
  query,
  rank,
}: CardProps<SummarySearchResultSchema>) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();
  const body = expanded
    ? result.content
    : snippetAround(result.content, query, SNIPPET_LIMIT);

  return (
    <CardFrame tone="summary" rank={rank}>
      <div className="search-result__top">
        <div className="search-result__identity">
          <span className="search-result__label">
            <Icon name="layers" size={15} className="search-result__kind-icon" />
            <span className="search-result__path search-result__path--static">
              Summary #{result.memory_summary_id}
            </span>
          </span>
          <span className="search-result__meta">
            <span>
              Period {formatDate(result.period_start)} – {formatDate(result.period_end)}
            </span>
          </span>
        </div>
        <div className="search-result__side">
          <MatchedByBadges matchedBy={result.matched_by} />
          <FusedScore value={result.score} />
        </div>
      </div>

      <p
        id={contentId}
        className={
          expanded
            ? "search-result__snippet search-result__snippet--full"
            : "search-result__snippet"
        }
      >
        {highlightTerms(body, query)}
      </p>

      {result.themes.length > 0 ? (
        <p className="search-result__themes" aria-label="Summary themes">
          {result.themes.map((theme, index) => (
            <span key={`${theme}-${index}`}>#{theme}</span>
          ))}
        </p>
      ) : null}

      <div className="search-result__foot">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Collapse summary" : "Read full summary"}
          <Icon name={expanded ? "chevron-down" : "chevron-right"} size={14} />
        </Button>
      </div>
    </CardFrame>
  );
}
