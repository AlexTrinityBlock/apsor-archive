import { ApiError } from "../../../apis/fetch-client";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";

/** The pre-query room: what the archive can retrieve and how to begin. */
export function SearchWelcome() {
  return (
    <section className="empty-state search-welcome">
      <div className="empty-state__icon">
        <Icon name="search" size={26} />
      </div>
      <p className="eyebrow">The archive is ready</p>
      <h2>Nothing is retrieved until you ask.</h2>
      <p className="empty-state__description">
        One query runs through a text lane and a vector lane. The fused candidates
        return as file chunks, memory crystals, and summaries, each with a real score
        and the lanes that matched it.
      </p>
      <div className="search-welcome__kinds" aria-label="Searchable source kinds">
        <span className="badge badge--moss">File chunks</span>
        <span className="badge badge--vermilion">Memory crystals</span>
        <span className="badge badge--ochre">Summaries</span>
      </div>
    </section>
  );
}

/** A quiet in-progress state while both retrieval lanes report back. */
export function SearchLoading() {
  return (
    <section className="search-loading" role="status" aria-live="polite">
      <Loader size={34} label="Searching the archive" />
      <div>
        <p className="eyebrow">Both lanes are running</p>
        <p className="search-loading__copy">
          BM25 and vector candidates are being merged, deduplicated, and fused.
        </p>
      </div>
    </section>
  );
}

interface SearchNoResultsProps {
  readonly query: string;
  readonly includeHistory: boolean;
  readonly isFetching: boolean;
  readonly onIncludeHistory: () => void;
  readonly onClear: () => void;
}

/** A searched-but-empty room with honest next moves. */
export function SearchNoResults({
  query,
  includeHistory,
  isFetching,
  onIncludeHistory,
  onClear,
}: SearchNoResultsProps) {
  return (
    <section className="empty-state search-noresults">
      <div className="empty-state__icon">
        <Icon name="search" size={26} />
      </div>
      <p className="eyebrow">No matching grain</p>
      <h2>Nothing matched “{query}”.</h2>
      <p className="empty-state__description">
        Try a shorter phrase or split the query into two concrete words.{" "}
        {includeHistory
          ? "History is already included, so superseded files and deprecated memories were searched too."
          : "Include history to search superseded files and deprecated memories."}
      </p>
      {isFetching ? (
        <p className="search-results__busy">
          <Loader size={12} label="Updating results" />
          Updating…
        </p>
      ) : null}
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

function errorParts(error: unknown): {
  readonly detail: string;
  readonly code: string;
  readonly status: number | null;
} {
  if (error instanceof ApiError) {
    return {
      detail: error.detail || "The archive did not answer.",
      code: error.code,
      status: error.status > 0 ? error.status : null,
    };
  }
  if (error instanceof Error) {
    return {
      detail: error.message || "The archive did not answer.",
      code: "unknown_error",
      status: null,
    };
  }
  return { detail: "The archive did not answer.", code: "unknown_error", status: null };
}

/** The failure state names the API error instead of hiding it behind a spinner. */
export function SearchError({ error, endpoint, onRetry }: SearchErrorProps) {
  const { detail, code, status } = errorParts(error);

  return (
    <section className="empty-state search-error" role="alert">
      <div className="empty-state__icon">
        <Icon name="info" size={26} />
      </div>
      <p className="eyebrow">Search interrupted</p>
      <h2>The archive did not answer.</h2>
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
