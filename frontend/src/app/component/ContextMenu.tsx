import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

import { Icon, type IconName } from "./Icon";
import "./ContextMenu.css";

export interface ContextMenuItem {
  readonly id: string;
  readonly label: string;
  readonly icon: IconName;
  readonly shortcut?: string;
  readonly danger?: boolean;
  readonly disabled?: boolean;
  readonly onSelect: () => void;
}

export interface ContextMenuProps {
  readonly x: number;
  readonly y: number;
  readonly items: readonly ContextMenuItem[];
  readonly label: string;
  readonly onClose: () => void;
  readonly returnFocus?: HTMLElement | null;
}

/** Gap kept between the menu and the viewport edge. */
const VIEWPORT_MARGIN = 8;

/** Collect the enabled (not disabled) item buttons, in the same order as the filtered items. */
function enabledElements(menu: HTMLDivElement): HTMLButtonElement[] {
  return Array.from(
    menu.querySelectorAll<HTMLButtonElement>(".context-menu__item:not(:disabled)"),
  );
}

/**
 * Shared context menu.
 *
 * Mounted in a portal on `document.body` so the Library's overflow or stacking
 * context cannot clip it; positioning is fixed, and after measuring it flips to
 * the left or upwards automatically.
 *
 * Keyboard: ArrowDown / ArrowUp / Home / End move focus, Enter / Space activate,
 * Escape / Tab close. When closing, `returnFocus` sends focus back to the
 * triggering element.
 */
export function ContextMenu({
  x,
  y,
  items,
  label,
  onClose,
  returnFocus,
}: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const returnFocusRef = useRef(returnFocus);
  const [position, setPosition] = useState({ left: x, top: y });
  const [measured, setMeasured] = useState(false);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    returnFocusRef.current = returnFocus;
  }, [returnFocus]);

  const closeMenu = useCallback(() => {
    onCloseRef.current();
  }, []);

  // Return focus to the trigger when the component unmounts (that is, on close).
  useEffect(() => {
    return () => {
      const target = returnFocusRef.current;
      if (target?.isConnected) {
        target.focus({ preventScroll: true });
      }
    };
  }, []);

  // Measure the real size first, then decide whether to flip left or up, so the
  // menu never sticks out of the viewport.
  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) {
      return;
    }
    const rect = menu.getBoundingClientRect();
    let left = x;
    let top = y;

    if (left + rect.width > window.innerWidth - VIEWPORT_MARGIN) {
      left = x - rect.width;
    }
    if (left < VIEWPORT_MARGIN) {
      left = VIEWPORT_MARGIN;
    }
    if (top + rect.height > window.innerHeight - VIEWPORT_MARGIN) {
      top = y - rect.height;
    }
    if (top < VIEWPORT_MARGIN) {
      top = VIEWPORT_MARGIN;
    }

    setPosition({ left, top });
    setMeasured(true);
  }, [x, y]);

  // On open, focus the first enabled item; if all are disabled, focus the menu itself.
  useEffect(() => {
    if (!measured) {
      return;
    }
    const menu = menuRef.current;
    const firstItem = menu ? enabledElements(menu)[0] : undefined;
    (firstItem ?? menu)?.focus({ preventScroll: true });
  }, [measured]);

  // Close the menu on an outside click, a viewport resize, or a scroll.
  useEffect(() => {
    const handleOutsideInteraction = (event: Event) => {
      // Clicks and overflow scrolling inside the menu itself must not close it.
      const menu = menuRef.current;
      if (menu && event.target instanceof Node && menu.contains(event.target)) {
        return;
      }
      closeMenu();
    };
    const handleResize = () => closeMenu();

    document.addEventListener("pointerdown", handleOutsideInteraction, true);
    window.addEventListener("resize", handleResize);
    document.addEventListener("scroll", handleOutsideInteraction, true);
    return () => {
      document.removeEventListener("pointerdown", handleOutsideInteraction, true);
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("scroll", handleOutsideInteraction, true);
    };
  }, [closeMenu]);

  const selectItem = useCallback(
    (item: ContextMenuItem) => {
      if (item.disabled) {
        return;
      }
      closeMenu();
      item.onSelect();
    },
    [closeMenu],
  );

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const menu = menuRef.current;
    if (!menu) {
      return;
    }

    const availableElements = enabledElements(menu);
    const availableItems = items.filter((item) => !item.disabled);
    const activeIndex = availableElements.findIndex(
      (element) => element === document.activeElement,
    );

    switch (event.key) {
      case "ArrowDown": {
        event.preventDefault();
        if (availableElements.length > 0) {
          const nextIndex = activeIndex < 0 ? 0 : (activeIndex + 1) % availableElements.length;
          availableElements[nextIndex]?.focus();
        }
        break;
      }
      case "ArrowUp": {
        event.preventDefault();
        if (availableElements.length > 0) {
          const nextIndex =
            activeIndex <= 0 ? availableElements.length - 1 : activeIndex - 1;
          availableElements[nextIndex]?.focus();
        }
        break;
      }
      case "Home":
        event.preventDefault();
        availableElements[0]?.focus();
        break;
      case "End":
        event.preventDefault();
        availableElements[availableElements.length - 1]?.focus();
        break;
      case "Enter":
      case " ": {
        event.preventDefault();
        event.stopPropagation();
        const activeItem = activeIndex >= 0 ? availableItems[activeIndex] : undefined;
        if (activeItem) {
          selectItem(activeItem);
        }
        break;
      }
      case "Escape":
      case "Tab":
        // Escape closes the menu; Tab is outside the menu's tab sequence, so it
        // closes and returns focus to the trigger.
        event.preventDefault();
        event.stopPropagation();
        closeMenu();
        break;
      default:
        break;
    }
  };

  return createPortal(
    <div
      ref={menuRef}
      className="context-menu"
      role="menu"
      aria-label={label}
      aria-orientation="vertical"
      tabIndex={-1}
      style={{
        left: position.left,
        top: position.top,
        visibility: measured ? "visible" : "hidden",
      }}
      onKeyDown={handleKeyDown}
      onContextMenu={(event) => event.preventDefault()}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          tabIndex={-1}
          className={[
            "context-menu__item",
            item.danger ? "context-menu__item--danger" : null,
          ]
            .filter(Boolean)
            .join(" ")}
          disabled={item.disabled}
          aria-disabled={item.disabled || undefined}
          onClick={() => selectItem(item)}
        >
          <Icon name={item.icon} size={15} className="context-menu__icon" />
          <span className="context-menu__label">{item.label}</span>
          {item.shortcut ? (
            <span className="context-menu__shortcut" aria-hidden="true">
              {item.shortcut}
            </span>
          ) : null}
        </button>
      ))}
    </div>,
    document.body,
  );
}
