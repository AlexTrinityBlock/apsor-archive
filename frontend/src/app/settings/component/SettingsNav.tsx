import { useEffect, useState } from "react";

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

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "true";
  } catch {
    return false;
  }
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
              onClick={() => setActive(section.id)}
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
