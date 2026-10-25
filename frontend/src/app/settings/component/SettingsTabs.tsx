import {
  useEffect,
  useLayoutEffect,
  useRef,
  type KeyboardEvent,
} from "react";

import { useI18n } from "../../i18n";
import {
  SETTINGS_SECTIONS,
  settingsTabId,
  type SettingsSectionId,
} from "./settings-sections";

interface SettingsTabsProps {
  readonly active: SettingsSectionId;
  readonly onSelect: (section: SettingsSectionId) => void;
}

/** Keep a small breathing room between the active tab and the scroll edges. */
const TAB_EDGE_MARGIN = 2;

/**
 * Horizontal settings tab strip. The list may overflow on narrow screens, so
 * it scrolls left and right instead of wrapping into an unpredictable height.
 */
export function SettingsTabs({ active, onSelect }: SettingsTabsProps) {
  const { t } = useI18n();
  const listRef = useRef<HTMLDivElement | null>(null);
  const tabRefs = useRef(new Map<SettingsSectionId, HTMLButtonElement>());
  const focusWasInListRef = useRef(false);

  // Browser back/forward can move focus to the fragment target after the tab
  // state changes. Capture the pre-navigation focus before that happens, and
  // expire the capture so a late event cannot affect a later navigation.
  useEffect(() => {
    let resetTimer = 0;
    const captureTabFocus = () => {
      window.clearTimeout(resetTimer);
      focusWasInListRef.current =
        listRef.current?.contains(document.activeElement) ?? false;
      resetTimer = window.setTimeout(() => {
        focusWasInListRef.current = false;
      }, 0);
    };
    window.addEventListener("popstate", captureTabFocus, true);
    window.addEventListener("hashchange", captureTabFocus, true);
    return () => {
      window.clearTimeout(resetTimer);
      window.removeEventListener("popstate", captureTabFocus, true);
      window.removeEventListener("hashchange", captureTabFocus, true);
    };
  }, []);

  // Selecting a tab centers it; later size changes only scroll when the active
  // tab is actually clipped, so resizes do not keep fighting manual scrolling.
  useLayoutEffect(() => {
    const list = listRef.current;
    const activeTab = tabRefs.current.get(active);
    if (!list || !activeTab) {
      return;
    }

    const revealActiveTab = (forceCenter: boolean) => {
      const listRect = list.getBoundingClientRect();
      const tabRect = activeTab.getBoundingClientRect();
      const fullyVisible =
        tabRect.left >= listRect.left + TAB_EDGE_MARGIN &&
        tabRect.right <= listRect.right - TAB_EDGE_MARGIN;
      if (!forceCenter && fullyVisible) {
        return;
      }
      const maxLeft = Math.max(0, list.scrollWidth - list.clientWidth);
      const centered =
        list.scrollLeft +
        (tabRect.left - listRect.left) -
        (list.clientWidth - tabRect.width) / 2;
      list.scrollLeft = Math.min(maxLeft, Math.max(0, centered));
    };

    revealActiveTab(true);
    const observer = new ResizeObserver(() => revealActiveTab(false));
    observer.observe(list);
    for (const tab of tabRefs.current.values()) {
      observer.observe(tab);
    }
    return () => observer.disconnect();
  }, [active]);

  // Restore focus to the newly selected tab after history navigation, but
  // never pull focus into the strip from skip links, body, or the sidebar.
  useLayoutEffect(() => {
    const list = listRef.current;
    const activeTab = tabRefs.current.get(active);
    const focusWasInList = focusWasInListRef.current;
    focusWasInListRef.current = false;
    if (!list || !activeTab) {
      return;
    }
    const focused = document.activeElement;
    const focusShouldFollow =
      focusWasInList || (focused !== null && list.contains(focused));
    if (!focusShouldFollow) {
      return;
    }

    const focusAlreadyOnActive = focused === activeTab;
    activeTab.focus({ preventScroll: true });
    if (!focusWasInList && focusAlreadyOnActive) {
      return;
    }
    // Chrome completes native fragment focus handling after the layout
    // effect, which can blur the tab back to the body. Reassert once the
    // navigation event's default action has finished.
    const frame = window.requestAnimationFrame(() => {
      activeTab.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [active]);

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const currentIndex = SETTINGS_SECTIONS.findIndex(
      (section) => settingsTabId(section.id) === event.currentTarget.id,
    );
    if (currentIndex < 0) {
      return;
    }

    let nextIndex: number;
    switch (event.key) {
      case "ArrowLeft":
        nextIndex =
          (currentIndex - 1 + SETTINGS_SECTIONS.length) %
          SETTINGS_SECTIONS.length;
        break;
      case "ArrowRight":
        nextIndex = (currentIndex + 1) % SETTINGS_SECTIONS.length;
        break;
      case "Home":
        nextIndex = 0;
        break;
      case "End":
        nextIndex = SETTINGS_SECTIONS.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    const next = SETTINGS_SECTIONS[nextIndex];
    onSelect(next.id);
    tabRefs.current.get(next.id)?.focus();
  };

  return (
    <div
      ref={listRef}
      className="settings-tabs"
      role="tablist"
      aria-label={t("core.settingsNav.aria")}
      aria-orientation="horizontal"
    >
      {SETTINGS_SECTIONS.map((section) => {
        const selected = section.id === active;
        const label = t(section.labelKey);
        return (
          <button
            key={section.id}
            ref={(element) => {
              if (element) {
                tabRefs.current.set(section.id, element);
              } else {
                tabRefs.current.delete(section.id);
              }
            }}
            type="button"
            role="tab"
            id={settingsTabId(section.id)}
            aria-selected={selected}
            aria-controls={section.id}
            tabIndex={selected ? 0 : -1}
            className={
              selected ? "settings-tabs__tab is-active" : "settings-tabs__tab"
            }
            title={label}
            onClick={() => onSelect(section.id)}
            onKeyDown={handleKeyDown}
          >
            <span className="settings-tabs__index" aria-hidden="true">
              {section.index}
            </span>
            <span className="settings-tabs__label">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
