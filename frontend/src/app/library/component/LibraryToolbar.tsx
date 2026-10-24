import { useId, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { LibraryBreadcrumbs } from "./LibraryBreadcrumbs";
import {
  LIBRARY_SORT_OPTIONS,
  type LibrarySort,
  type LibraryTab,
  type LibraryView,
} from "./library-utils";

interface LibraryToolbarProps {
  readonly path: string;
  readonly tab: LibraryTab;
  readonly rawQuery: string;
  readonly activeQuery: string;
  readonly sort: LibrarySort;
  readonly view: LibraryView;
  readonly selecting: boolean;
  readonly folderCount: number;
  readonly fileCount: number;
  readonly mediaCount: number;
  readonly loading: boolean;
  readonly settling: boolean;
  readonly onNavigate: (path: string) => void;
  readonly onQueryChange: (value: string) => void;
  readonly onQuerySubmit: (value: string) => void;
  readonly onClearQuery: () => void;
  readonly onSortChange: (sort: LibrarySort) => void;
  readonly onTabChange: (tab: LibraryTab) => void;
  readonly onViewChange: (view: LibraryView) => void;
  readonly onToggleSelecting: () => void;
  readonly onUpload: () => void;
  readonly onNewFolder: () => void;
}

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function StatusLine({
  tab,
  activeQuery,
  folderCount,
  fileCount,
  mediaCount,
  loading,
  settling,
}: Pick<
  LibraryToolbarProps,
  | "tab"
  | "activeQuery"
  | "folderCount"
  | "fileCount"
  | "mediaCount"
  | "loading"
  | "settling"
>) {
  if (loading) {
    return <span className="library-status library-status--busy">Reading the shelf…</span>;
  }
  if (tab === "media") {
    return (
      <span className="library-status">
        {countLabel(mediaCount, "image", "images")} in this folder
      </span>
    );
  }
  if (settling) {
    return <span className="library-status library-status--busy">Reading paths…</span>;
  }
  if (activeQuery) {
    return (
      <span className="library-status">
        {countLabel(fileCount, "match", "matches")} for <code>“{activeQuery}”</code>
      </span>
    );
  }
  return (
    <span className="library-status">
      {countLabel(folderCount, "folder", "folders")} · {countLabel(fileCount, "file", "files")}
    </span>
  );
}

/**
 * The compact library header: breadcrumb, fuzzy path search, client-side sort,
 * primary actions, tab strip, and the files-only board/list and select controls.
 */
export function LibraryToolbar({
  path,
  tab,
  rawQuery,
  activeQuery,
  sort,
  view,
  selecting,
  folderCount,
  fileCount,
  mediaCount,
  loading,
  settling,
  onNavigate,
  onQueryChange,
  onQuerySubmit,
  onClearQuery,
  onSortChange,
  onTabChange,
  onViewChange,
  onToggleSelecting,
  onUpload,
  onNewFolder,
}: LibraryToolbarProps) {
  const searchId = useId();
  const sortId = useId();

  const handleSearchSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onQuerySubmit(rawQuery.trim());
  };

  return (
    <header className="library-topbar">
      <div className="library-topbar__row">
        <div className="library-topbar__lead">
          <LibraryBreadcrumbs path={path} onNavigate={onNavigate} />
        </div>

        <div className="library-topbar__tools">
          {tab === "files" ? (
            <>
              <form className="library-search-mini" role="search" onSubmit={handleSearchSubmit}>
                <span className="library-search-mini__icon" aria-hidden="true">
                  <Icon name="search" size={14} />
                </span>
                <label className="visually-hidden" htmlFor={searchId}>
                  Fuzzy search file paths
                </label>
                <input
                  id={searchId}
                  type="search"
                  value={rawQuery}
                  onChange={(event) => onQueryChange(event.target.value)}
                  placeholder="Search files and folders…"
                  autoComplete="off"
                  spellCheck={false}
                />
                {rawQuery.length > 0 ? (
                  <button
                    type="button"
                    className="library-search-mini__clear"
                    onClick={onClearQuery}
                    aria-label="Clear fuzzy search"
                  >
                    <Icon name="close" size={13} />
                  </button>
                ) : null}
              </form>

              <label className="library-sort" htmlFor={sortId}>
                <span className="visually-hidden">Sort files</span>
                <Icon name="arrow-down" size={13} className="library-sort__icon" />
                <select
                  id={sortId}
                  className="library-sort__select"
                  value={sort}
                  onChange={(event) => onSortChange(event.target.value as LibrarySort)}
                >
                  {LIBRARY_SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      Sort: {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : null}

          <Button variant="secondary" size="sm" onClick={onUpload}>
            <Icon name="arrow-down" size={14} />
            Upload
          </Button>
          <Button variant="ink" size="sm" onClick={onNewFolder}>
            <Icon name="folder" size={14} />
            New folder
          </Button>
        </div>
      </div>

      <div className="library-viewstrip">
        <div className="tabs" role="tablist" aria-label="Library workspace">
          <button
            type="button"
            role="tab"
            id="library-tab-files"
            aria-selected={tab === "files"}
            aria-controls="library-panel"
            className={tab === "files" ? "tab is-active" : "tab"}
            onClick={() => onTabChange("files")}
          >
            Files
            {loading ? null : <span className="library-tab-count">{fileCount}</span>}
          </button>
          <button
            type="button"
            role="tab"
            id="library-tab-media"
            aria-selected={tab === "media"}
            aria-controls="library-panel"
            className={tab === "media" ? "tab is-active" : "tab"}
            onClick={() => onTabChange("media")}
          >
            Media gallery
            {loading ? null : <span className="library-tab-count">{mediaCount}</span>}
          </button>
        </div>

        <div className="library-viewstrip__meta">
          <StatusLine
            tab={tab}
            activeQuery={activeQuery}
            folderCount={folderCount}
            fileCount={fileCount}
            mediaCount={mediaCount}
            loading={loading}
            settling={settling}
          />

          {tab === "files" ? (
            <div className="library-viewstrip__controls">
              <div className="library-view-toggle" role="group" aria-label="File view">
                <button
                  type="button"
                  className={
                    view === "board" ? "library-view-toggle__btn is-active" : "library-view-toggle__btn"
                  }
                  aria-pressed={view === "board"}
                  onClick={() => onViewChange("board")}
                >
                  <Icon name="layers" size={13} />
                  Board
                </button>
                <button
                  type="button"
                  className={
                    view === "list" ? "library-view-toggle__btn is-active" : "library-view-toggle__btn"
                  }
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
                onClick={onToggleSelecting}
                disabled={!selecting && fileCount === 0}
              >
                <Icon name="check" size={13} />
                {selecting ? "Selecting" : "Select"}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
