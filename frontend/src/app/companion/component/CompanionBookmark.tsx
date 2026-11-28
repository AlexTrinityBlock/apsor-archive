import type { CSSProperties, Ref } from "react";

import { Icon } from "../../component/Icon";
import type { BookmarkPlacement } from "../layout";
import type { CompanionCharacter } from "../manifest";

export const BOOKMARK_HEIGHT = 56;

interface CompanionBookmarkProps {
  readonly ref?: Ref<HTMLButtonElement>;
  readonly character: CompanionCharacter;
  readonly left: boolean;
  readonly placement: BookmarkPlacement;
  readonly label: string;
  readonly hidden: boolean;
  readonly onActivate: () => void;
}

/**
 * The companion tucked away as a ribbon bookmark at the visible window edge.
 * Used both when the reader minimizes it and when there is no room to show
 * the figure; activating it brings the figure back.
 */
export function CompanionBookmark({
  ref,
  character,
  left,
  placement,
  label,
  hidden,
  onActivate,
}: CompanionBookmarkProps) {
  const style = {
    top: placement.top,
    left: left ? placement.left : undefined,
    right: left ? undefined : placement.right,
    "--companion-accent": character.accent,
  } as CSSProperties;
  return (
    <button
      ref={ref}
      type="button"
      className={`companion-bookmark${left ? " is-left" : ""}`}
      style={style}
      onClick={onActivate}
      aria-label={label}
      title={label}
      hidden={hidden}
    >
      <svg className="companion-bookmark__ribbon" viewBox="0 0 34 56" aria-hidden="true" focusable="false">
        <path d="M3 0h28a3 3 0 0 1 3 3v53l-17-11-17 11V3a3 3 0 0 1 3-3z" />
      </svg>
      {character.portrait !== null ? (
        <img
          className="companion-bookmark__portrait"
          src={character.portrait}
          alt=""
          width={22}
          height={22}
          draggable={false}
        />
      ) : (
        <span className="companion-bookmark__glyph" aria-hidden="true">
          <Icon name="user" size={12} />
        </span>
      )}
    </button>
  );
}
