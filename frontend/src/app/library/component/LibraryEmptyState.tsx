import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface LibraryEmptyStateProps {
  readonly path: string;
  readonly query: string;
  readonly seeding: boolean;
  readonly onUpload: () => void;
  readonly onNewFolder: () => void;
  readonly onClearSearch: () => void;
  readonly onOpenRoot: () => void;
  readonly onSeed: () => void;
}

/** Empty, first-run, and no-match states for the Files tab. */
export function LibraryEmptyState({
  path,
  query,
  seeding,
  onUpload,
  onNewFolder,
  onClearSearch,
  onOpenRoot,
  onSeed,
}: LibraryEmptyStateProps) {
  const { t } = useI18n();
  if (query) {
    return (
      <EmptyState
        icon="search"
        eyebrow={t("library.empty.searchEyebrow")}
        title={t("library.empty.noMatchTitle", { query })}
        description={t("library.empty.noMatchDescription")}
        className="library-empty"
        action={
          <Button variant="secondary" size="sm" onClick={onClearSearch}>
            {t("library.empty.clearSearch")}
          </Button>
        }
      />
    );
  }

  const isRoot = path === "/";
  return (
    <EmptyState
      icon={isRoot ? "library" : "folder"}
      eyebrow={
        isRoot ? t("library.empty.firstRunEyebrow") : t("library.empty.folderEyebrow")
      }
      title={isRoot ? t("library.empty.rootTitle") : t("library.empty.folderTitle")}
      description={
        isRoot
          ? t("library.empty.rootDescription")
          : t("library.empty.folderDescription", { path })
      }
      className="library-empty"
      aside={
        <span className="library-dropzone__hint">
          <Icon name="arrow-down" size={14} />
          {t("library.empty.dropZone")}
        </span>
      }
      action={
        <div className="empty-state__actions">
          <Button variant="ink" size="sm" onClick={onUpload}>
            <Icon name="plus" size={15} />
            {t("library.common.uploadFile")}
          </Button>
          <Button variant="secondary" size="sm" onClick={onNewFolder}>
            <Icon name="folder" size={15} />
            {t("library.common.newFolder")}
          </Button>
          {isRoot ? (
            <Button variant="ghost" size="sm" onClick={onSeed} disabled={seeding} aria-busy={seeding}>
              {seeding ? t("library.empty.seeding") : t("library.empty.seed")}
              {seeding ? null : <Icon name="spark" size={15} />}
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={onOpenRoot}>
              {t("library.common.backToRoot")}
            </Button>
          )}
        </div>
      }
    />
  );
}
