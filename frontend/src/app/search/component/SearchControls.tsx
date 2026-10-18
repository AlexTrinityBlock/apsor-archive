import { SearchField } from "../../component/SearchField";

const RESULT_NUMBER_OPTIONS = Array.from({ length: 10 }, (_, index) => index + 1);

interface SearchControlsProps {
  readonly query: string;
  readonly onQueryChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly resultNumber: number;
  readonly onResultNumberChange: (value: number) => void;
  readonly includeHistory: boolean;
  readonly onIncludeHistoryChange: (value: boolean) => void;
}

/**
 * The shared search field plus the two knobs that change the request shape.
 * Every control writes to the URL, so refresh and history navigation agree.
 */
export function SearchControls({
  query,
  onQueryChange,
  onSubmit,
  resultNumber,
  onResultNumberChange,
  includeHistory,
  onIncludeHistoryChange,
}: SearchControlsProps) {
  return (
    <section className="search-controls" aria-label="Search controls">
      <SearchField
        value={query}
        onChange={onQueryChange}
        onSubmit={onSubmit}
        label="Search the archive"
        placeholder="Try a phrase, a path, or a half-remembered detail..."
        submitLabel="Search"
        size="lg"
        autoFocus
      />

      <div className="search-controls__bar">
        <label className="search-controls__field">
          <span className="search-controls__label">Results per kind</span>
          <select
            className="search-controls__select"
            value={resultNumber}
            onChange={(event) => onResultNumberChange(Number(event.target.value))}
          >
            {RESULT_NUMBER_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          role="switch"
          aria-checked={includeHistory}
          className="search-history"
          onClick={() => onIncludeHistoryChange(!includeHistory)}
        >
          <span className="search-history__track" aria-hidden="true">
            <span className="search-history__knob" />
          </span>
          <span className="search-history__copy">
            <span>Include history</span>
            <small>Superseded files and deprecated memories</small>
          </span>
        </button>
      </div>

      <p className="search-controls__hint">
        Each lane keeps up to N per source kind. The URL keeps the query, N, and
        history setting, so back and forward replay the same search.
      </p>
    </section>
  );
}
