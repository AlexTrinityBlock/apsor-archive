import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../component/PageHeader";
import { useI18n } from "../i18n";
import { DiagnosticsPanel } from "./component/DiagnosticsPanel";
import { FrequentlyUsedPromptsPanel } from "./component/FrequentlyUsedPromptsPanel";
import { LanguagePanel } from "./component/LanguagePanel";
import { MaintenancePanel } from "./component/MaintenancePanel";
import { ProviderVaultPanel } from "./component/ProviderVaultPanel";
import {
  AgentRuntimeSettingsPanel,
  IngestRuntimeSettingsPanel,
} from "./component/RuntimeSettingsPanels";
import {
  defaultSettingsSection,
  isSettingsSectionVisible,
  parseSettingsSectionHash,
  selectSettingsSections,
  settingsSectionFromHash,
  settingsTabId,
  type SettingsSectionId,
} from "./component/settings-sections";
import { SettingsTabs } from "./component/SettingsTabs";
import { SystemPromptPanel } from "./component/SystemPromptPanel";
import "./settings.css";

const SECTION_PANELS: Record<SettingsSectionId, ComponentType> = {
  "settings-system-prompt": SystemPromptPanel,
  "settings-frequent-prompts": FrequentlyUsedPromptsPanel,
  "settings-providers": ProviderVaultPanel,
  "settings-diagnostics": DiagnosticsPanel,
  "settings-agent-runtime": AgentRuntimeSettingsPanel,
  "settings-ingest-runtime": IngestRuntimeSettingsPanel,
  "settings-maintenance": MaintenancePanel,
  "settings-language": LanguagePanel,
};

function readSectionFromLocation(isRoot: boolean): SettingsSectionId {
  return parseSettingsSectionHash(window.location.hash, isRoot);
}

/**
 * Empty hashes mean the first visible tab; unknown hashes mean "keep the
 * current tab"; a known but role-hidden section falls back to the first tab.
 */
function sectionFromHash(
  hash: string,
  isRoot: boolean,
  fallback: SettingsSectionId,
): SettingsSectionId | null {
  if (hash === "" || hash === "#") {
    return fallback;
  }
  const section = settingsSectionFromHash(hash);
  if (section === null) {
    return null;
  }
  return isSettingsSectionVisible(section, isRoot) ? section : fallback;
}

/** Keep the fixed shell canvas aligned with the newly mounted tab. */
function resetCanvasScroll(): void {
  window.scrollTo({ top: 0, behavior: "instant" });
  document.querySelector<HTMLElement>(".app-page")?.scrollTo({
    top: 0,
    behavior: "instant",
  });
}

/**
 * Settings: a top tab strip that mounts one section at a time. Root accounts
 * see the global configuration tabs; every other account only sees personal
 * prompts and interface language. Keeping inactive panels unmounted avoids the
 * long anchor scroll and the blank canvas that appeared when the language
 * switch changed the whole document layout.
 */
export function SettingsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isRoot = user?.role === "root";
  const sections = useMemo(() => selectSettingsSections(isRoot), [isRoot]);
  const sectionIds = useMemo(
    () => new Set(sections.map((section) => section.id)),
    [sections],
  );
  const fallbackSection = defaultSettingsSection(isRoot);
  const location = useLocation();
  const navigate = useNavigate();
  const [active, setActive] = useState<SettingsSectionId>(() =>
    readSectionFromLocation(isRoot),
  );
  const [syncedRoute, setSyncedRoute] = useState({
    hash: location.hash,
    key: location.key,
  });

  // React Router navigations (including the sidebar removing the hash) must
  // adjust the tab during render rather than from an effect: setState-in-effect
  // is disallowed here, and this is the documented previous-value pattern.
  if (
    syncedRoute.hash !== location.hash ||
    syncedRoute.key !== location.key
  ) {
    setSyncedRoute({ hash: location.hash, key: location.key });
    const section = sectionFromHash(location.hash, isRoot, fallbackSection);
    if (section !== null) {
      setActive(section);
    }
  }

  // A role change or a deep link to a hidden tab can leave the stored section
  // outside the visible list. Resolve it during render to avoid a hidden panel.
  if (!sectionIds.has(active)) {
    setActive(fallbackSection);
  }

  const syncActiveToHash = useCallback(
    (hash: string) => {
      const section = sectionFromHash(hash, isRoot, fallbackSection);
      if (section !== null) {
        setActive(section);
      }
    },
    [fallbackSection, isRoot, setActive],
  );

  // Native hash edits and skip links do not always pass through the router.
  useEffect(() => {
    const syncFromWindowHash = () => syncActiveToHash(window.location.hash);
    window.addEventListener("hashchange", syncFromWindowHash);
    window.addEventListener("popstate", syncFromWindowHash);
    return () => {
      window.removeEventListener("hashchange", syncFromWindowHash);
      window.removeEventListener("popstate", syncFromWindowHash);
    };
  }, [syncActiveToHash]);

  // Rewrite a hidden deep link to the section that is actually visible. Unknown
  // hashes (for example the skip link's #main-content) are left untouched.
  useEffect(() => {
    const hashSection = settingsSectionFromHash(location.hash);
    if (hashSection === null || sectionIds.has(hashSection)) {
      return;
    }
    navigate(
      {
        pathname: location.pathname,
        search: location.search,
        hash: `#${fallbackSection}`,
      },
      { replace: true, preventScrollReset: true },
    );
  }, [
    fallbackSection,
    location.hash,
    location.pathname,
    location.search,
    navigate,
    sectionIds,
  ]);

  useLayoutEffect(() => {
    resetCanvasScroll();
  }, [active]);

  const selectSection = useCallback(
    (section: SettingsSectionId) => {
      if (!sectionIds.has(section)) {
        return;
      }
      setActive(section);
      resetCanvasScroll();
      if (window.location.hash !== `#${section}`) {
        navigate(
          {
            pathname: location.pathname,
            search: location.search,
            hash: `#${section}`,
          },
          { preventScrollReset: true },
        );
      }
    },
    [location.pathname, location.search, navigate, sectionIds, setActive],
  );

  const ActivePanel = SECTION_PANELS[active];

  return (
    <div className="content-container settings-page">
      <div className="settings-content">
        <PageHeader
          eyebrow={t(
            isRoot ? "settings.page.eyebrow" : "settings.page.personalEyebrow",
          )}
          title={t(
            isRoot ? "settings.page.title" : "settings.page.personalTitle",
          )}
          description={t(
            isRoot
              ? "settings.page.description"
              : "settings.page.personalDescription",
          )}
          meta={
            <span>
              {t(
                isRoot ? "settings.page.meta" : "settings.page.personalMeta",
              )}
            </span>
          }
        />

        <SettingsTabs
          active={active}
          sections={sections}
          onSelect={selectSection}
        />

        <div
          id={active}
          className="settings-tabpanel"
          role="tabpanel"
          aria-labelledby={settingsTabId(active)}
        >
          <ActivePanel />
        </div>
      </div>
    </div>
  );
}
