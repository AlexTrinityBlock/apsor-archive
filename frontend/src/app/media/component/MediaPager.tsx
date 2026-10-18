import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";

interface MediaPagerProps {
  readonly offset: number;
  readonly pageSize: number;
  readonly total: number;
  readonly onOffsetChange: (offset: number) => void;
}

/** Paper-sheet pagination for the visual archive. */
export function MediaPager({ offset, pageSize, total, onOffsetChange }: MediaPagerProps) {
  if (total <= pageSize) {
    return null;
  }

  const start = Math.min(offset + 1, total);
  const end = Math.min(offset + pageSize, total);
  const previousOffset = Math.max(0, offset - pageSize);
  const nextOffset = offset + pageSize;

  return (
    <nav className="media-pager" aria-label="Media archive pages">
      <Button
        variant="secondary"
        size="sm"
        onClick={() => onOffsetChange(previousOffset)}
        disabled={offset === 0}
      >
        <Icon name="arrow-right" size={14} className="media-back-icon" />
        Previous
      </Button>
      <span className="media-pager__position">
        Images {start}–{end} of {total}
      </span>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => onOffsetChange(nextOffset)}
        disabled={end >= total}
      >
        Next
        <Icon name="arrow-right" size={14} />
      </Button>
    </nav>
  );
}
