import type { KeyboardEvent } from "react";

/**
 * WAI-ARIA tabs keyboard model: Left/Right wrap, Home/End jump. Returns the
 * index to activate, or null when the key is not a tab-navigation key.
 */
export function nextTabIndex(
  key: string,
  index: number,
  count: number,
): number | null {
  if (count <= 0) {
    return null;
  }
  switch (key) {
    case "ArrowRight":
      return (index + 1) % count;
    case "ArrowLeft":
      return (index - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

/**
 * Handle a keydown on a tablist with automatic activation: the next tab is
 * selected and focused. `tabId` maps a tab value to its element id.
 */
export function handleTabListKeyDown<T extends string>(
  event: KeyboardEvent<HTMLElement>,
  tabs: readonly T[],
  current: T,
  onSelect: (tab: T) => void,
  tabId: (tab: T) => string,
): void {
  const next = nextTabIndex(event.key, tabs.indexOf(current), tabs.length);
  if (next === null) {
    return;
  }
  event.preventDefault();
  const tab = tabs[next];
  if (tab === undefined) {
    return;
  }
  onSelect(tab);
  document.getElementById(tabId(tab))?.focus();
}
