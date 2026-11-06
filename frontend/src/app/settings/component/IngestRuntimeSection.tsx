import { IngestRuntimeSettingsPanel } from "./RuntimeSettingsPanels";
import { VisionPromptSettingsPanel } from "./VisionPromptSettingsPanel";

/**
 * The ingestion runtime tab: the existing worker/chunking/language form first,
 * then the separate vision prompt editor. Prompt persistence is deliberately
 * not part of the runtime settings snapshot above it.
 */
export function IngestRuntimeSection() {
  return (
    <div className="settings-stack">
      <IngestRuntimeSettingsPanel />
      <VisionPromptSettingsPanel />
    </div>
  );
}
