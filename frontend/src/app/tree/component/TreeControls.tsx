import { useState, type FormEvent, type ReactNode } from "react";

import { normalizeTreeRoot } from "../treeLayout";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { SearchField } from "../../component/SearchField";

const MIN_DEPTH = 3;
const MAX_DEPTH = 20;
const DEPTH_OPTIONS = Array.from(
  { length: MAX_DEPTH - MIN_DEPTH + 1 },
  (_, index) => MIN_DEPTH + index,
);

interface Breadcrumb {
  readonly label: string;
  readonly path: string;
}

interface TreeControlsProps {
  readonly rootPath: string;
  readonly depth: number;
  readonly includeHistory: boolean;
  readonly breadcrumbs: readonly Breadcrumb[];
  readonly searchDraft: string;
  readonly searchActive: boolean;
  readonly searchBusy: boolean;
  readonly searchFailed: boolean;
  readonly searchMatchCount: number;
  readonly onReadRoot: (root: string) => void;
  readonly onDepthChange: (depth: string) => void;
  readonly onToggleHistory: () => void;
  readonly onBreadcrumb: (path: string) => void;
  readonly onSearchChange: (value: string) => void;
  readonly onSearchSubmit: (value: string) => void;
}

interface RootFormProps {
  readonly rootPath: string;
  readonly onReadRoot: (root: string) => void;
}

function RootForm({ rootPath, onReadRoot }: RootFormProps) {
  const [draft, setDraft] = useState(rootPath);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = normalizeTreeRoot(draft);
    setDraft(normalized);
    onReadRoot(normalized);
  };

  return (
    <form className="tree-root" onSubmit={handleSubmit}>
      <label className="eyebrow" htmlFor="tree-root-input">
        Root path
      </label>
      <div className="tree-root__field">
        <Icon name="folder" size={16} />
        <input
          id="tree-root-input"
          name="root"
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          spellCheck={false}
          autoComplete="off"
          placeholder="/"
        />
        <Button type="submit" variant="ink" size="sm">
          Read
        </Button>
      </div>
    </form>
  );
}

interface SearchStatusProps {
  readonly active: boolean;
  readonly busy: boolean;
  readonly failed: boolean;
  readonly matchCount: number;
  readonly draft: string;
}

function SearchStatus({ active, busy, failed, matchCount, draft }: SearchStatusProps) {
  let content: ReactNode;
  if (busy) {
    content = <Badge tone="neutral">searching</Badge>;
  } else if (failed) {
    content = <Badge tone="neutral">search unavailable</Badge>;
  } else if (active) {
    content = (
      <Badge tone="vermilion">
        {matchCount} {matchCount === 1 ? "match" : "matches"}
      </Badge>
    );
  } else if (draft.length > 0) {
    content = (
      <span className="tree-search__hint">
        Type at least two characters to highlight files.
      </span>
    );
  } else {
    content = (
      <span className="tree-search__hint">
        Matches get a vermilion ring, without leaving the tree.
      </span>
    );
  }

  return (
    <div className="tree-search__status" aria-live="polite">
      {content}
    </div>
  );
}

/** URL-backed controls for root, depth, history, local search, and breadcrumbs. */
export function TreeControls({
  rootPath,
  depth,
  includeHistory,
  breadcrumbs,
  searchDraft,
  searchActive,
  searchBusy,
  searchFailed,
  searchMatchCount,
  onReadRoot,
  onDepthChange,
  onToggleHistory,
  onBreadcrumb,
  onSearchChange,
  onSearchSubmit,
}: TreeControlsProps) {
  return (
    <section
      className="tree-controls reveal reveal-2"
      aria-label="Knowledge tree controls"
    >
      <RootForm key={rootPath} rootPath={rootPath} onReadRoot={onReadRoot} />

      <div className="tree-controls__group">
        <label className="tree-field">
          <span className="eyebrow">Depth</span>
          <select
            className="tree-select"
            value={depth}
            onChange={(event) => onDepthChange(event.target.value)}
          >
            {DEPTH_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className={includeHistory ? "tree-toggle is-on" : "tree-toggle"}
          aria-pressed={includeHistory}
          onClick={onToggleHistory}
        >
          <span className="tree-toggle__track" aria-hidden="true">
            <span className="tree-toggle__thumb" />
          </span>
          <span className="tree-toggle__copy">
            <span className="eyebrow">History</span>
            <span>Include retired branches</span>
          </span>
        </button>
      </div>

      <div className="tree-search">
        <SearchField
          value={searchDraft}
          onChange={onSearchChange}
          onSubmit={onSearchSubmit}
          label="Highlight tree files by content"
          placeholder="Highlight files by content..."
          submitLabel="Find"
        />
        <SearchStatus
          active={searchActive}
          busy={searchBusy}
          failed={searchFailed}
          matchCount={searchMatchCount}
          draft={searchDraft}
        />
      </div>

      <nav className="tree-breadcrumb" aria-label="Tree root breadcrumb">
        {breadcrumbs.map((crumb, index) => (
          <span className="tree-breadcrumb__slot" key={crumb.path}>
            <button
              type="button"
              className="tree-breadcrumb__item"
              aria-current={index === breadcrumbs.length - 1 ? "page" : undefined}
              onClick={() => onBreadcrumb(crumb.path)}
            >
              {crumb.label}
            </button>
            {index < breadcrumbs.length - 1 ? (
              <span className="tree-breadcrumb__slash" aria-hidden="true">
                /
              </span>
            ) : null}
          </span>
        ))}
      </nav>
    </section>
  );
}
