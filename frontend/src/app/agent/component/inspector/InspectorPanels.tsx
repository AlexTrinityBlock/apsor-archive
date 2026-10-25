import { ToolErrorPanel } from "./ErrorPanel";
import { ReadMemoryPanel, SaveMemoryPanel } from "./MemoryPanels";
import { PresentResourcePanel } from "./PresentResourcePanel";
import { ReadFilePanel } from "./ReadFilePanel";
import { ReadPathPanel } from "./ReadPathPanel";
import { ReadTimelinePanel } from "./ReadTimelinePanel";
import { SearchKnowledgePanel } from "./SearchKnowledgePanel";
import { WebFetchPanel, WebSearchPanel } from "./WebPanels";
import type { PanelProps } from "./common";

/** Generic fallback for an unrecognized but recorded tool. */
function UnknownToolPanel({ item }: PanelProps) {
  return (
    <div className="pi-unknown">
      <p className="eyebrow">Recorded tool</p>
      <strong>{item.tool ?? item.name}</strong>
      <p>
        This tool has no dedicated inspector panel. Its arguments, status, and
        structured preview remain visible below.
      </p>
    </div>
  );
}

/**
 * Route one trace item to its distinctive workbench panel.
 *
 * Errors always win, so a failed read_file still opens the repair bench rather
 * than pretending it has a manuscript window.
 */
export function InspectorPanel({ item }: PanelProps) {
  if (item.status.toLowerCase() === "error" || item.kind === "error") {
    return <ToolErrorPanel item={item} />;
  }
  switch (item.tool) {
    case "search_knowledge":
      return <SearchKnowledgePanel item={item} />;
    case "read_file":
      return <ReadFilePanel item={item} />;
    case "read_timeline":
      return <ReadTimelinePanel item={item} />;
    case "read_path":
      return <ReadPathPanel item={item} />;
    case "read_memory":
      return <ReadMemoryPanel item={item} />;
    case "save_memory":
      return <SaveMemoryPanel item={item} />;
    case "present_resource":
      return <PresentResourcePanel item={item} />;
    case "web_search":
      return <WebSearchPanel item={item} />;
    case "web_fetch":
      return <WebFetchPanel item={item} />;
    default:
      return <UnknownToolPanel item={item} />;
  }
}

export { ToolErrorPanel };
