import { useEffect, useState } from "react";

import { Icon } from "../../component/Icon";

interface SettingsSection {
  readonly id: string;
  readonly label: string;
  readonly index: string;
}

const SECTIONS: readonly SettingsSection[] = [
  { id: "settings-system-prompt", label: "System prompt", index: "01" },
  {
    id: "settings-frequent-prompts",
    label: "Frequent prompts",
    index: "02",
  },
  { id: "settings-providers", label: "Provider registry", index: "03" },
  { id: "settings-diagnostics", label: "Diagnostics", index: "04" },
  { id: "settings-agent-runtime", label: "Agent runtime", index: "05" },
  {
    id: "settings-ingest-runtime",
    label: "Ingestion runtime",
    index: "06",
  },
  { id: "settings-maintenance", label: "Maintenance", index: "07" },
];

const COLLAPSE_KEY = "dendromatrix.settings.navCollapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "true";
  } catch {
    return false;
  }
}

/** Sticky settings sub-navigation; a drawer strip on mobile. */
export function SettingsNav() {
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
      aria-label="Settings sections"
    >
      <div className="settings-nav__head">
        <span className="settings-nav__title">
          <span className="mono-label">Settings</span>
          <span className="settings-nav__count">{SECTIONS.length} sections</span>
        </span>
        <button
          type="button"
          className="settings-nav__toggle"
          onClick={() => setCollapsed((current) => !current)}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand settings navigation" : "Collapse settings navigation"}
          title={collapsed ? "Expand settings navigation" : "Collapse settings navigation"}
        >
          <Icon name={collapsed ? "chevron-right" : "chevron-down"} size={14} />
        </button>
      </div>

      <nav className="settings-nav__links">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            className={
              active === section.id
                ? "settings-nav__link is-active"
                : "settings-nav__link"
            }
            title={section.label}
            onClick={() => setActive(section.id)}
          >
            <span className="settings-nav__index">{section.index}</span>
            <span className="settings-nav__label">{section.label}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}
