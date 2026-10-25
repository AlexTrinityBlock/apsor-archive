import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  type ComponentType,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";

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
  DEFAULT_SETTINGS_SECTION,
  parseSettingsSectionHash,
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

function readSectionFromLocation(): SettingsSectionId {
  return parseSettingsSectionHash(window.location.hash);
}

/** Empty hashes mean the first tab; unknown hashes mean "keep the current tab". */
function sectionFromHash(hash: string): SettingsSectionId | null {
  if (hash === "" || hash === "#") {
    return DEFAULT_SETTINGS_SECTION;
  }
  return settingsSectionFromHash(hash);
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
 * Settings: a top tab strip that mounts one section at a time. Keeping the
 * inactive panels unmounted avoids the long anchor scroll and the blank canvas
 * that appeared when the language switch changed the whole document layout.
 */
export function SettingsPage() {
  const { t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const [active, setActive] = useState<SettingsSectionId>(
    readSectionFromLocation,
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
    const section = sectionFromHash(location.hash);
    if (section !== null) {
      setActive(section);
    }
  }

  const syncActiveToHash = useCallback((hash: string) => {
    const section = sectionFromHash(hash);
    if (section !== null) {
      setActive(section);
    }
  }, []);

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

  useLayoutEffect(() => {
    resetCanvasScroll();
  }, [active]);

  const selectSection = useCallback(
    (section: SettingsSectionId) => {
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
    [location.pathname, location.search, navigate],
  );

  const ActivePanel = SECTION_PANELS[active];

  return (
    <div className="content-container settings-page">
      <div className="settings-content">
        <PageHeader
          eyebrow={t("settings.page.eyebrow")}
          title={t("settings.page.title")}
          description={t("settings.page.description")}
          meta={<span>{t("settings.page.meta")}</span>}
        />

        <SettingsTabs active={active} onSelect={selectSection} />

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
