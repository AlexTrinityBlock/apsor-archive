import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface LibrarySelectionBarProps {
  readonly selectedCount: number;
  readonly visibleCount: number;
  readonly onSelectAll: () => void;
  readonly onClear: () => void;
  readonly onMoveSelected: () => void;
  readonly onExit: () => void;
}

/**
 * Batch-move controls for the library. It sits outside the board and list so
 * both views, including the narrow-screen list, expose the same actions.
 */
export function LibrarySelectionBar({
  selectedCount,
  visibleCount,
  onSelectAll,
  onClear,
  onMoveSelected,
  onExit,
}: LibrarySelectionBarProps) {
  const { t, formatNumber } = useI18n();
  const allSelected = visibleCount > 0 && selectedCount === visibleCount;

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
            ? "library.selection.countOne"
            : "library.selection.countOther",
        )}
        <span className="library-selection-bar__hint">
          {t("library.selection.visible", { count: formatNumber(visibleCount) })}
        </span>
      </p>
      <div className="library-selection-bar__actions">
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
          disabled={selectedCount === 0}
        >
          <Icon name="branch" size={14} />
          {t("library.selection.moveSelected")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onExit}>
          {t("library.common.done")}
        </Button>
      </div>
    </div>
  );
}
