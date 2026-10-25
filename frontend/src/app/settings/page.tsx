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
import { SettingsNav } from "./component/SettingsNav";
import { SystemPromptPanel } from "./component/SystemPromptPanel";
import "./settings.css";

/**
 * Settings: frequent prompts, the unified provider registry, live diagnostics,
 * runtime limits, and archive maintenance. The template is light-only, so no
 * theme control is exposed here.
 */
export function SettingsPage() {
  const { t } = useI18n();
  return (
    <div className="content-container settings-page">
      <div className="settings-layout">
        <SettingsNav />

        <div className="settings-content">
          <PageHeader
            eyebrow={t("settings.page.eyebrow")}
            title={t("settings.page.title")}
            description={t("settings.page.description")}
            meta={<span>{t("settings.page.meta")}</span>}
          />

          <SystemPromptPanel />

          <FrequentlyUsedPromptsPanel />

          <div id="settings-providers" className="settings-anchor">
            <ProviderVaultPanel />
          </div>
          <div id="settings-diagnostics" className="settings-anchor">
            <DiagnosticsPanel />
          </div>
          <div id="settings-agent-runtime" className="settings-anchor">
            <AgentRuntimeSettingsPanel />
          </div>
          <div id="settings-ingest-runtime" className="settings-anchor">
            <IngestRuntimeSettingsPanel />
          </div>
          <div id="settings-maintenance" className="settings-anchor">
            <MaintenancePanel />
          </div>
          <div id="settings-language" className="settings-anchor">
            <LanguagePanel />
          </div>
        </div>
      </div>
    </div>
  );
}
