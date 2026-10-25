import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface LibrarySelectionBarProps {
  readonly selectedFileCount: number;
  readonly selectedFolderCount: number;
  readonly visibleCount: number;
  readonly onSelectAll: () => void;
  readonly onClear: () => void;
  readonly onMoveSelected: () => void;
  readonly onDeleteSelected: () => void;
  readonly onExit: () => void;
}

/**
 * Batch actions for the library. It sits outside the board and list so both
 * views, including the narrow-screen list, expose the same file and folder
 * actions. Folders are delete-only, so a folder selection locks batch move.
 */
export function LibrarySelectionBar({
  selectedFileCount,
  selectedFolderCount,
  visibleCount,
  onSelectAll,
  onClear,
  onMoveSelected,
  onDeleteSelected,
  onExit,
}: LibrarySelectionBarProps) {
  const { t, formatNumber } = useI18n();
  const selectedCount = selectedFileCount + selectedFolderCount;
  const allSelected = visibleCount > 0 && selectedCount === visibleCount;
  const moveBlockedByFolders = selectedFolderCount > 0;
  const moveDisabled = selectedFileCount === 0 || moveBlockedByFolders;

  return (
    <div
      className="library-selection-bar reveal"
      role="region"
      aria-label={t("library.selection.aria")}
    >
      <p className="library-selection-bar__count" role="status" aria-live="polite">
        <Icon name="check" size={14} />
        <strong>{formatNumber(selectedCount)}</strong>{" "}
        {t(
          selectedCount === 1
            ? "library.selection.totalOne"
            : "library.selection.totalOther",
        )}
        <span className="library-selection-bar__breakdown">
          {t(
            selectedFileCount === 1
              ? "library.selection.filesOne"
              : "library.selection.filesOther",
            { count: formatNumber(selectedFileCount) },
          )}
          <span aria-hidden="true"> · </span>
          {t(
            selectedFolderCount === 1
              ? "library.selection.foldersOne"
              : "library.selection.foldersOther",
            { count: formatNumber(selectedFolderCount) },
          )}
        </span>
        <span className="library-selection-bar__hint">
          {t("library.selection.visible", { count: formatNumber(visibleCount) })}
        </span>
      </p>
      <div className="library-selection-bar__actions">
        {selectedFolderCount > 0 ? (
          <span className="library-selection-bar__note">
            {t("library.selection.foldersOnlyHint")}
          </span>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          onClick={allSelected ? onClear : onSelectAll}
          disabled={visibleCount === 0}
        >
          {allSelected
            ? t("library.selection.clearSelection")
            : t("library.selection.selectAll")}
        </Button>
        {selectedCount > 0 && !allSelected ? (
          <Button variant="ghost" size="sm" onClick={onClear}>
            {t("library.common.clear")}
          </Button>
        ) : null}
        <Button
          variant="primary"
          size="sm"
          onClick={onMoveSelected}
          disabled={moveDisabled}
          title={
            moveBlockedByFolders
              ? t("library.selection.foldersOnlyHint")
              : undefined
          }
        >
          <Icon name="branch" size={14} />
          {t("library.selection.moveSelected")}
        </Button>
        <Button
          variant="danger"
          size="sm"
          className="library-selection-bar__delete"
          onClick={onDeleteSelected}
          disabled={selectedCount === 0}
        >
          <Icon name="trash" size={14} />
          {t("library.selection.deleteSelected")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onExit}>
          {t("library.common.done")}
        </Button>
      </div>
    </div>
  );
}
