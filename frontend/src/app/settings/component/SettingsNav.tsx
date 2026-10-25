import { useEffect, useState, type MouseEvent } from "react";

import { Icon } from "../../component/Icon";
import { useI18n, type TranslationKey } from "../../i18n";

interface SettingsSection {
  readonly id: string;
  readonly labelKey: TranslationKey;
  readonly index: string;
}

const SECTIONS: readonly SettingsSection[] = [
  { id: "settings-system-prompt", labelKey: "core.settingsNav.systemPrompt", index: "01" },
  {
    id: "settings-frequent-prompts",
    labelKey: "core.settingsNav.frequentPrompts",
    index: "02",
  },
  { id: "settings-providers", labelKey: "core.settingsNav.providers", index: "03" },
  { id: "settings-diagnostics", labelKey: "core.settingsNav.diagnostics", index: "04" },
  { id: "settings-agent-runtime", labelKey: "core.settingsNav.agentRuntime", index: "05" },
  {
    id: "settings-ingest-runtime",
    labelKey: "core.settingsNav.ingestRuntime",
    index: "06",
  },
  { id: "settings-maintenance", labelKey: "core.settingsNav.maintenance", index: "07" },
  { id: "settings-language", labelKey: "core.settingsNav.language", index: "08" },
];

const COLLAPSE_KEY = "apsor-archive.settings.navCollapsed";
const SCROLL_OFFSET = 18;

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * Scroll the settings canvas, not the window.
 *
 * The archive shell is a fixed 100dvh layout with `.app-page` as its scroll
 * container. A native hash jump scrolls every scrollable ancestor, including
 * the document, which shifts the fixed rail upward and leaves a large blank
 * area below the last section. Reset the document first, then move only the
 * inner canvas.
 */
function scrollToSection(id: string, behavior: ScrollBehavior = "smooth"): void {
  window.scrollTo(0, 0);
  const target = document.getElementById(id);
  const canvas = document.querySelector<HTMLElement>(".app-page");
  if (!target || !canvas) {
    return;
  }
  const stacked = window.matchMedia("(max-width: 980px)").matches;
  const nav = document.querySelector<HTMLElement>(".settings-nav");
  const offset =
    stacked && nav ? Math.round(nav.getBoundingClientRect().height) + 10 : SCROLL_OFFSET;
  const targetRect = target.getBoundingClientRect();
  const canvasRect = canvas.getBoundingClientRect();
  const top = canvas.scrollTop + targetRect.top - canvasRect.top - offset;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  canvas.scrollTo({
    top: Math.max(0, top),
    behavior: reducedMotion ? "auto" : behavior,
  });
}

/** Sticky settings sub-navigation; a drawer strip on mobile. */
export function SettingsNav() {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [active, setActive] = useState(() => {
    const hash = window.location.hash.replace("#", "");
    return SECTIONS.some((section) => section.id === hash) ? hash : SECTIONS[0].id;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSE_KEY, String(collapsed));
    } catch {
      // Storage can be blocked; the local state still works.
    }
  }, [collapsed]);

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (!SECTIONS.some((section) => section.id === hash)) {
      return;
    }

    // The panels load asynchronously and grow the document after the first
    // paint. Keep the requested section aligned while that layout settles,
    // then stop so manual scrolling is never fought.
    let settleTimer = 0;
    const align = () => scrollToSection(hash, "auto");
    const content = document.querySelector<HTMLElement>(".settings-content");
    const observer = new ResizeObserver(() => {
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(align, 80);
    });
    if (content) {
      observer.observe(content);
    }
    const initial = window.setTimeout(align, 120);
    const stop = window.setTimeout(() => observer.disconnect(), 5000);
    const stopOnInput = () => observer.disconnect();
    window.addEventListener("wheel", stopOnInput, { once: true, passive: true });
    window.addEventListener("touchstart", stopOnInput, {
      once: true,
      passive: true,
    });

    return () => {
      window.clearTimeout(settleTimer);
      window.clearTimeout(initial);
      window.clearTimeout(stop);
      window.removeEventListener("wheel", stopOnInput);
      window.removeEventListener("touchstart", stopOnInput);
      observer.disconnect();
    };
  }, []);

  const handleNavigate = (event: MouseEvent<HTMLAnchorElement>, id: string) => {
    event.preventDefault();
    setActive(id);
    window.history.pushState(null, "", `#${id}`);
    scrollToSection(id);
  };

  return (
    <aside
      className={collapsed ? "settings-nav is-collapsed" : "settings-nav"}
      aria-label={t("core.settingsNav.aria")}
    >
      <div className="settings-nav__head">
        <span className="settings-nav__title">
          <span className="mono-label">{t("core.settingsNav.title")}</span>
          <span className="settings-nav__count">
            {t("core.settingsNav.sectionCount", { count: SECTIONS.length })}
          </span>
        </span>
        <button
          type="button"
          className="settings-nav__toggle"
          onClick={() => setCollapsed((current) => !current)}
          aria-expanded={!collapsed}
          aria-label={
            collapsed
              ? t("core.settingsNav.expand")
              : t("core.settingsNav.collapse")
          }
          title={
            collapsed
              ? t("core.settingsNav.expand")
              : t("core.settingsNav.collapse")
          }
        >
          <Icon name={collapsed ? "chevron-right" : "chevron-down"} size={14} />
        </button>
      </div>

      <nav className="settings-nav__links">
        {SECTIONS.map((section) => {
          const label = t(section.labelKey);
          return (
            <a
              key={section.id}
              href={`#${section.id}`}
              className={
                active === section.id
                  ? "settings-nav__link is-active"
                  : "settings-nav__link"
              }
              title={label}
              onClick={(event) => handleNavigate(event, section.id)}
            >
              <span className="settings-nav__index">{section.index}</span>
              <span className="settings-nav__label">{label}</span>
            </a>
          );
        })}
      </nav>
    </aside>
  );
}
