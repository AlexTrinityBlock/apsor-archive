import { useGetStats } from "../../generated-apis-types/system/system";
import { useI18n, type TranslationKey } from "../../i18n";

export type LibraryCollection = "files" | "media" | "memories";

interface LibraryTabStripProps {
  readonly active: LibraryCollection;
  /** Counts for the current folder listing; omitted while loading. */
  readonly fileCount?: number | null;
  readonly mediaCount?: number | null;
  readonly onSelect: (collection: LibraryCollection) => void;
}

const TABS: readonly {
  readonly collection: LibraryCollection;
  readonly labelKey: TranslationKey;
}[] = [
  { collection: "files", labelKey: "library.toolbar.filesTab" },
  { collection: "media", labelKey: "library.toolbar.mediaTab" },
  { collection: "memories", labelKey: "library.toolbar.memoriesTab" },
];

/** The tab id used by the shared `library-panel` tabpanel. */
export function libraryTabId(collection: LibraryCollection): string {
  return `library-tab-${collection}`;
}

/**
 * Files · Media · Memories. Files and Media share one folder listing; Memories
 * is a separate collection, so its count comes from the archive statistics.
 */
export function LibraryTabStrip({
  active,
  fileCount,
  mediaCount,
  onSelect,
}: LibraryTabStripProps) {
  const { t, formatNumber } = useI18n();
  const stats = useGetStats();
  const memoryCount = stats.data?.memory_count ?? null;
  const counts: Record<LibraryCollection, number | null | undefined> = {
    files: fileCount,
    media: mediaCount,
    memories: memoryCount,
  };

  return (
    <div className="tabs" role="tablist" aria-label={t("library.toolbar.workspaceTabs")}>
      {TABS.map(({ collection, labelKey }) => {
        const count = counts[collection];
        const selected = active === collection;
        return (
          <button
            key={collection}
            type="button"
            role="tab"
            id={libraryTabId(collection)}
            aria-selected={selected}
            aria-controls="library-panel"
            className={selected ? "tab is-active" : "tab"}
            onClick={() => onSelect(collection)}
          >
            {t(labelKey)}
            {count === null || count === undefined ? null : (
              <span
                className="library-tab-count"
                aria-label={
                  collection === "memories"
                    ? t("library.toolbar.memoriesTabCountAria", { count })
                    : undefined
                }
              >
                {formatNumber(count)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
