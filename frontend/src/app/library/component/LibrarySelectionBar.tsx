import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";

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
  const allSelected = visibleCount > 0 && selectedCount === visibleCount;

  return (
    <div className="library-selection-bar reveal" role="region" aria-label="Batch file selection">
      <p className="library-selection-bar__count" role="status" aria-live="polite">
        <Icon name="check" size={14} />
        <strong>{selectedCount}</strong> {selectedCount === 1 ? "file" : "files"} selected
        <span className="library-selection-bar__hint">
          {visibleCount} visible in this folder
        </span>
      </p>
      <div className="library-selection-bar__actions">
        <Button
          variant="ghost"
          size="sm"
          onClick={allSelected ? onClear : onSelectAll}
          disabled={visibleCount === 0}
        >
          {allSelected ? "Clear selection" : "Select all visible"}
        </Button>
        {selectedCount > 0 && !allSelected ? (
          <Button variant="ghost" size="sm" onClick={onClear}>
            Clear
          </Button>
        ) : null}
        <Button
          variant="primary"
          size="sm"
          onClick={onMoveSelected}
          disabled={selectedCount === 0}
        >
          <Icon name="branch" size={14} />
          Move selected
        </Button>
        <Button variant="ghost" size="sm" onClick={onExit}>
          Done
        </Button>
      </div>
    </div>
  );
}
