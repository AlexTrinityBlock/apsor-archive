import { Link } from "react-router-dom";

import { ApiError } from "../../../apis/fetch-client";
import { Button } from "../../component/Button";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { buildSearchUrl } from "./url";

const SUGGESTED_QUERIES = [
  "automobile history",
  "Ford Model T",
  "automatic transmission",
  "brake line",
] as const;

/** The pre-query room: what the archive can do and where to begin. */
export function SearchWelcome() {
  return (
    <section className="empty-state search-welcome reveal reveal-3">
      <div className="empty-state__rings" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="empty-state__icon">
        <Icon name="search" size={28} />
      </div>
      <p className="eyebrow">The archive is ready</p>
      <h2>Nothing is retrieved until you ask.</h2>
      <p className="empty-state__description">
        A query runs through two lanes: BM25 for literal grain and vector
        similarity for near meaning. Reciprocal-rank fusion keeps the passages
        both lanes agree on, then each source kind gets its own shelf.
      </p>

      <div className="search-welcome__suggestions">
        <span className="search-welcome__label">Follow a vein</span>
        {SUGGESTED_QUERIES.map((suggestion) => (
          <Link key={suggestion} className="suggestion" to={buildSearchUrl(suggestion)}>
            {suggestion}
          </Link>
        ))}
      </div>

      <ol className="search-welcome__steps" aria-label="How hybrid search runs">
        <li>
          <span>01</span>
          <div>
            <strong>Text lane</strong>
            <p>BM25 scores CJK bigrams, words, and partial spellings.</p>
          </div>
        </li>
        <li>
          <span>02</span>
          <div>
            <strong>Vector lane</strong>
            <p>Cosine similarity finds passages close in meaning.</p>
          </div>
        </li>
        <li>
          <span>03</span>
          <div>
            <strong>Fuse once</strong>
            <p>Duplicates collapse and RRF orders the surviving grain.</p>
          </div>
        </li>
      </ol>
    </section>
  );
}

/** A quiet in-progress state while both retrieval lanes report back. */
export function SearchLoading() {
  return (
    <section className="search-loading reveal reveal-3" role="status" aria-live="polite">
      <Loader size={38} label="Searching the archive" />
      <div>
        <p className="eyebrow">Both lanes are running</p>
        <p>BM25 and vector candidates are being fused before the shelves open.</p>
      </div>
    </section>
  );
}

interface SearchNoResultsProps {
  readonly query: string;
  readonly includeHistory: boolean;
  readonly onIncludeHistory: () => void;
  readonly onClear: () => void;
}

/** A searched-but-empty room with honest next moves. */
export function SearchNoResults({
  query,
  includeHistory,
  onIncludeHistory,
  onClear,
}: SearchNoResultsProps) {
  return (
    <section className="empty-state search-noresults reveal reveal-3">
      <div className="empty-state__icon">
        <Icon name="search" size={28} />
      </div>
      <p className="eyebrow">No matching grain</p>
      <h2>Nothing matched “{query}”.</h2>
      <p className="empty-state__description">
        Try a shorter phrase, split the query into two concrete words, or open
        the history branch. Deprecated memories and superseded file versions do
        not enter the default search surface.
      </p>
      <div className="empty-state__actions">
        {!includeHistory ? (
          <Button variant="secondary" size="sm" onClick={onIncludeHistory}>
            <Icon name="history" size={15} />
            Include history
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear query
        </Button>
      </div>
    </section>
  );
}

interface SearchErrorProps {
  readonly error: unknown;
  readonly endpoint: string;
  readonly onRetry: () => void;
}

function errorDetail(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "The archive did not answer.";
}

/** The failure state names the API error instead of hiding it behind a spinner. */
export function SearchError({ error, endpoint, onRetry }: SearchErrorProps) {
  const detail = errorDetail(error);
  const code = error instanceof ApiError ? error.code : "unknown_error";
  const status = error instanceof ApiError && error.status > 0 ? error.status : null;

  return (
    <section className="empty-state search-error reveal reveal-3" role="alert">
      <div className="empty-state__icon">
        <Icon name="info" size={28} />
      </div>
      <p className="eyebrow">Search interrupted</p>
      <h2>The two lanes did not report back.</h2>
      <p className="empty-state__description">{detail}</p>

      <div className="search-error__meta">
        <Badge tone="vermilion">{code}</Badge>
        {status !== null ? <span>HTTP {status}</span> : <span>Network request</span>}
      </div>

      <div className="endpoint-label">
        <span>GET</span>
        <code>{endpoint}</code>
      </div>

      <div className="empty-state__actions">
        <Button variant="secondary" size="sm" onClick={onRetry}>
          <Icon name="search" size={15} />
          Try again
        </Button>
      </div>
    </section>
  );
}
