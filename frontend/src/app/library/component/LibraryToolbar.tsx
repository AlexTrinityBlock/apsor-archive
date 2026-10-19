import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { SearchField } from "../../component/SearchField";
import type { LibraryView } from "./library-utils";
import { LibraryBreadcrumbs } from "./LibraryBreadcrumbs";

interface LibraryToolbarProps {
  readonly path: string;
  readonly rawQuery: string;
  readonly activeQuery: string;
  readonly folderCount: number;
  readonly fileCount: number;
  readonly loading: boolean;
  readonly settling: boolean;
  readonly view: LibraryView;
  readonly onNavigate: (path: string) => void;
  readonly onQueryChange: (value: string) => void;
  readonly onQuerySubmit: (value: string) => void;
  readonly onClearQuery: () => void;
  readonly onViewChange: (view: LibraryView) => void;
  readonly selecting: boolean;
  readonly onToggleSelecting: () => void;
}

type SearchStatusProps = Pick<
  LibraryToolbarProps,
  "activeQuery" | "folderCount" | "fileCount" | "loading" | "settling" | "onClearQuery"
>;

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function SearchStatus({
  activeQuery,
  folderCount,
  fileCount,
  loading,
  settling,
  onClearQuery,
}: SearchStatusProps) {
  if (loading) {
    return (
      <span className="library-toolbar__reading">
        {activeQuery ? "Reading path matches…" : "Reading the current shelf…"}
      </span>
    );
  }
  if (settling) {
    return <span className="library-toolbar__reading">Reading paths…</span>;
  }
  if (activeQuery) {
    return (
      <>
        <span className="eyebrow">Paths matching</span>
        <code>“{activeQuery}”</code>
        <span className="library-toolbar__count">{countLabel(fileCount, "match", "matches")}</span>
        <Button variant="ghost" size="sm" onClick={onClearQuery}>
          Clear
        </Button>
      </>
    );
  }
  return (
    <span className="library-toolbar__count">
      {countLabel(folderCount, "folder", "folders")} ·{" "}
      {countLabel(fileCount, "file", "files")} in this directory
    </span>
  );
}

/** Breadcrumb trail plus the fuzzy path field and its result status. */
export function LibraryToolbar({
  path,
  rawQuery,
  activeQuery,
  folderCount,
  fileCount,
  loading,
  settling,
  onNavigate,
  onQueryChange,
  onQuerySubmit,
  onClearQuery,
  view,
  onViewChange,
  selecting,
  onToggleSelecting,
}: LibraryToolbarProps) {
  return (
    <div className="library-toolbar reveal reveal-2">
      <div className="library-toolbar__path">
        <p className="eyebrow">Archive path</p>
        <LibraryBreadcrumbs path={path} onNavigate={onNavigate} />
      </div>
      <div className="library-toolbar__search">
        <SearchField
          value={rawQuery}
          onChange={onQueryChange}
          onSubmit={onQuerySubmit}
          label="Fuzzy search file paths"
          placeholder="Fuzzy search paths…"
          submitLabel="Find paths"
        />
        <div className="library-toolbar__status" aria-live="polite">
          <SearchStatus
            activeQuery={activeQuery}
            folderCount={folderCount}
            fileCount={fileCount}
            loading={loading}
            settling={settling}
            onClearQuery={onClearQuery}
          />
          <div className="library-view-toggle" role="group" aria-label="Library view">
            <button
              type="button"
              className={view === "board" ? "library-view-toggle__btn is-active" : "library-view-toggle__btn"}
              aria-pressed={view === "board"}
              onClick={() => onViewChange("board")}
            >
              <Icon name="layers" size={13} />
              Board
            </button>
            <button
              type="button"
              className={view === "list" ? "library-view-toggle__btn is-active" : "library-view-toggle__btn"}
              aria-pressed={view === "list"}
              onClick={() => onViewChange("list")}
            >
              <Icon name="menu" size={13} />
              List
            </button>
          </div>
          <button
            type="button"
            className={selecting ? "library-select-toggle is-active" : "library-select-toggle"}
            aria-pressed={selecting}
            aria-label={selecting ? "Exit batch selection" : "Select files for batch move"}
            onClick={onToggleSelecting}
            disabled={!selecting && fileCount === 0}
          >
            <Icon name="check" size={13} />
            {selecting ? "Selecting" : "Select"}
          </button>
        </div>
      </div>
    </div>
  );
}
