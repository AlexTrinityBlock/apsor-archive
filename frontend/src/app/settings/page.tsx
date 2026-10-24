import { PageHeader } from "../component/PageHeader";
import { DiagnosticsPanel } from "./component/DiagnosticsPanel";
import { MaintenancePanel } from "./component/MaintenancePanel";
import { ProviderVaultPanel } from "./component/ProviderVaultPanel";
import {
  AgentRuntimeSettingsPanel,
  IngestRuntimeSettingsPanel,
} from "./component/RuntimeSettingsPanels";
import "./settings.css";

/**
 * Settings: the database-backed AI vault, live diagnostics, runtime limits,
 * and archive maintenance. The template is light-only, so no theme control is
 * exposed here.
 */
export function SettingsPage() {
  return (
    <div className="content-container content-container--form settings-page">
      <PageHeader
        eyebrow="Settings · system configuration"
        title="System settings & provider vault."
        description="Configure the two AI provider slots, inspect live service diagnostics, and calibrate the ingestion and agent runtime limits. Stored keys stay on the server and are never returned to this page."
        meta={<span>Settings 07 · local-first archive</span>}
      />

      <ProviderVaultPanel />
      <DiagnosticsPanel />
      <AgentRuntimeSettingsPanel />
      <IngestRuntimeSettingsPanel />
      <MaintenancePanel />
    </div>
  );
}
