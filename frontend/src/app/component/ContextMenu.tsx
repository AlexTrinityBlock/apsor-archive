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

/** 選單與 viewport 邊緣之間保留的距離。 */
const VIEWPORT_MARGIN = 8;

/** 取得目前可用（未 disabled）的選單項目按鈕，順序與 items 過濾後一致。 */
function enabledElements(menu: HTMLDivElement): HTMLButtonElement[] {
  return Array.from(
    menu.querySelectorAll<HTMLButtonElement>(".context-menu__item:not(:disabled)"),
  );
}

/**
 * 通用右鍵選單。
 *
 * 以 portal 掛到 `document.body`，避免被 Library 的 overflow 或 stacking
 * context 裁切；定位使用 fixed，並在量測後自動往左／往上翻轉。
 *
 * 鍵盤操作：ArrowDown / ArrowUp / Home / End 移動焦點，Enter / Space 觸發，
 * Escape / Tab 關閉。關閉時若有 `returnFocus`，焦點會回到觸發元素。
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

  // 元件卸載（亦即選單關閉）時把焦點還給觸發元素。
  useEffect(() => {
    return () => {
      const target = returnFocusRef.current;
      if (target?.isConnected) {
        target.focus({ preventScroll: true });
      }
    };
  }, []);

  // 先量測實際尺寸，再決定是否往左或往上翻，避免選單突出 viewport。
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

  // 開啟時聚焦第一個可用項目；若全部 disabled，則聚焦選單本身。
  useEffect(() => {
    if (!measured) {
      return;
    }
    const menu = menuRef.current;
    const firstItem = menu ? enabledElements(menu)[0] : undefined;
    (firstItem ?? menu)?.focus({ preventScroll: true });
  }, [measured]);

  // 點擊外部、viewport 尺寸改變或捲動時關閉選單。
  useEffect(() => {
    const handleOutsideInteraction = (event: Event) => {
      // 選單自身的點擊與 overflow 捲動不應該把自己關掉。
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
        // Escape 關閉選單；Tab 不屬於選單的 tab 序列，直接關閉並回到觸發元素。
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
