import { PageHeader } from "../component/PageHeader";
import { DiagnosticsPanel } from "./component/DiagnosticsPanel";
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
 * Settings: the custom system prompt, AI vault, live diagnostics, runtime
 * limits, and archive maintenance. The template is light-only, so no theme
 * control is exposed here.
 */
export function SettingsPage() {
  return (
    <div className="content-container settings-page">
      <div className="settings-layout">
        <SettingsNav />

        <div className="settings-content">
          <PageHeader
            eyebrow="Settings · system configuration"
            title="System settings & provider vault."
            description="Write the first section of every new conversation, configure the two AI provider slots, inspect live service diagnostics, and calibrate the ingestion and agent runtime limits. Stored keys stay on the server and are never returned to this page."
            meta={<span>Settings 07 · local-first archive</span>}
          />

          <SystemPromptPanel />

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
        </div>
      </div>
    </div>
  );
}
