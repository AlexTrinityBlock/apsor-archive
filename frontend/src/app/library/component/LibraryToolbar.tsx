import { useId, type FormEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n, type TranslationKey } from "../../i18n";
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
  readonly onNewMarkdown: () => void;
}

const SORT_LABEL_KEYS: Record<LibrarySort, TranslationKey> = {
  modified: "library.sort.modified",
  name: "library.sort.name",
  size: "library.sort.size",
  type: "library.sort.type",
};

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
  const { t, formatNumber } = useI18n();
  if (loading) {
    return (
      <span className="library-status library-status--busy">
        {t("library.toolbar.readingShelf")}
      </span>
    );
  }
  if (tab === "media") {
    return (
      <span className="library-status">
        {t(
          mediaCount === 1
            ? "library.toolbar.mediaStatusOne"
            : "library.toolbar.mediaStatusOther",
          { count: formatNumber(mediaCount) },
        )}
      </span>
    );
  }
  if (settling) {
    return (
      <span className="library-status library-status--busy">
        {t("library.toolbar.readingPaths")}
      </span>
    );
  }
  if (activeQuery) {
    return (
      <span className="library-status">
        {t(
          fileCount === 1
            ? "library.toolbar.matchStatusOne"
            : "library.toolbar.matchStatusOther",
          { count: formatNumber(fileCount), query: activeQuery },
        )}
      </span>
    );
  }
  return (
    <span className="library-status">
      {t(
        folderCount === 1
          ? "library.units.folderOne"
          : "library.units.folderOther",
        { count: formatNumber(folderCount) },
      )}
      {" · "}
      {t(fileCount === 1 ? "library.units.fileOne" : "library.units.fileOther", {
        count: formatNumber(fileCount),
      })}
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
  onNewMarkdown,
}: LibraryToolbarProps) {
  const { t, formatNumber } = useI18n();
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
                  {t("library.toolbar.searchLabel")}
                </label>
                <input
                  id={searchId}
                  type="search"
                  value={rawQuery}
                  onChange={(event) => onQueryChange(event.target.value)}
                  placeholder={t("library.toolbar.searchPlaceholder")}
                  autoComplete="off"
                  spellCheck={false}
                />
                {rawQuery.length > 0 ? (
                  <button
                    type="button"
                    className="library-search-mini__clear"
                    onClick={onClearQuery}
                    aria-label={t("library.toolbar.clearSearch")}
                  >
                    <Icon name="close" size={13} />
                  </button>
                ) : null}
              </form>

              <label className="library-sort" htmlFor={sortId}>
                <span className="visually-hidden">{t("library.sort.label")}</span>
                <Icon name="arrow-down" size={13} className="library-sort__icon" />
                <select
                  id={sortId}
                  className="library-sort__select"
                  value={sort}
                  onChange={(event) => onSortChange(event.target.value as LibrarySort)}
                >
                  {LIBRARY_SORT_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {t("library.sort.prefix", { label: t(SORT_LABEL_KEYS[option]) })}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : null}

          <Button variant="secondary" size="sm" onClick={onUpload}>
            <Icon name="arrow-down" size={14} />
            {t("library.common.upload")}
          </Button>
          <Button variant="secondary" size="sm" onClick={onNewMarkdown}>
            <Icon name="plus" size={14} />
            {t("library.editor.newNote")}
          </Button>
          <Button variant="ink" size="sm" onClick={onNewFolder}>
            <Icon name="folder" size={14} />
            {t("library.common.newFolder")}
          </Button>
        </div>
      </div>

      <div className="library-viewstrip">
        <div className="tabs" role="tablist" aria-label={t("library.toolbar.workspaceTabs")}>
          <button
            type="button"
            role="tab"
            id="library-tab-files"
            aria-selected={tab === "files"}
            aria-controls="library-panel"
            className={tab === "files" ? "tab is-active" : "tab"}
            onClick={() => onTabChange("files")}
          >
            {t("library.toolbar.filesTab")}
            {loading ? null : (
              <span className="library-tab-count">{formatNumber(fileCount)}</span>
            )}
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
            {t("library.toolbar.mediaTab")}
            {loading ? null : (
              <span className="library-tab-count">{formatNumber(mediaCount)}</span>
            )}
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
              <div
                className="library-view-toggle"
                role="group"
                aria-label={t("library.toolbar.viewLabel")}
              >
                <button
                  type="button"
                  className={
                    view === "board" ? "library-view-toggle__btn is-active" : "library-view-toggle__btn"
                  }
                  aria-pressed={view === "board"}
                  onClick={() => onViewChange("board")}
                >
                  <Icon name="layers" size={13} />
                  {t("library.toolbar.board")}
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
                  {t("library.toolbar.list")}
                </button>
              </div>
              <button
                type="button"
                className={selecting ? "library-select-toggle is-active" : "library-select-toggle"}
                aria-pressed={selecting}
                onClick={onToggleSelecting}
                disabled={!selecting && fileCount === 0 && folderCount === 0}
              >
                <Icon name="check" size={13} />
                {selecting ? t("library.toolbar.selecting") : t("library.toolbar.select")}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
