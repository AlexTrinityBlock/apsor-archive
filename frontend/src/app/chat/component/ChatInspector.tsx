import type { RefObject } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { AgentInspector } from "../../agent/component/AgentInspector";
import { InspectorFileStage } from "../../agent/component/inspector/common";
import {
  viewerHref,
  type ResourceTarget,
  type WorkTraceModel,
} from "../../agent/trace";

export type InspectorTab = "telemetry" | "preview";

interface ChatInspectorProps {
  readonly inspectorRef: RefObject<HTMLElement | null>;
  readonly tab: InspectorTab;
  readonly onTab: (tab: InspectorTab) => void;
  readonly trace: WorkTraceModel;
  readonly pinnedId: string | null;
  readonly onFollow: () => void;
  readonly previewTarget: ResourceTarget | null;
  readonly onCollapse: () => void;
  readonly narrow: boolean;
}

function PreviewEmpty() {
  return (
    <div className="empty-state chat-preview__empty">
      <span className="empty-state__icon" aria-hidden="true">
        <Icon name="file" size={20} />
      </span>
      <h2 className="empty-state__title">No document selected</h2>
      <p className="empty-state__description">
        Open a file citation, or a file resource from a tool result, to preview
        it in place.
      </p>
    </div>
  );
}

function ChatPreview({ target }: { readonly target: ResourceTarget | null }) {
  if (!target) {
    return <PreviewEmpty />;
  }

  const openLabel =
    target.type === "file" ? "Open in library" : "Open memory";

  return (
    <div className="chat-preview">
      <header className="chat-preview__head">
        <div>
          <p className="mono-label">Document preview</p>
          <strong>{target.title ?? `File #${target.id}`}</strong>
          <code>
            file:{target.id}
            {target.chunk === null ? "" : ` · chunk ${target.chunk}`}
          </code>
        </div>
        <Link className="text-link" to={viewerHref(target)}>
          {openLabel}
          <Icon name="arrow-up-right" size={12} />
        </Link>
      </header>
      <div className="chat-preview__scroll">
        <InspectorFileStage fileId={target.id} chunk={target.chunk} />
      </div>
    </div>
  );
}

/** The inspector column: tool telemetry and in-situ document preview. */
export function ChatInspector({
  inspectorRef,
  tab,
  onTab,
  trace,
  pinnedId,
  onFollow,
  previewTarget,
  onCollapse,
  narrow,
}: ChatInspectorProps) {
  return (
    <aside
      ref={inspectorRef}
      className="panel chat-inspector"
      aria-label="Inspector"
    >
      <div className="chat-inspector__bar">
        <div className="tabs tabs--light chat-inspector__tabs" role="tablist" aria-label="Inspector views">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "telemetry"}
            className={tab === "telemetry" ? "tab is-active" : "tab"}
            onClick={() => onTab("telemetry")}
          >
            <Icon name="command" size={12} />
            Tool Telemetry
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "preview"}
            className={tab === "preview" ? "tab is-active" : "tab"}
            onClick={() => onTab("preview")}
          >
            <Icon name="file" size={12} />
            Document Preview
          </button>
        </div>
        {!narrow ? (
          <button
            type="button"
            className="chat-icon-btn chat-inspector__collapse"
            onClick={onCollapse}
            aria-label="Collapse inspector"
            title="Collapse inspector"
          >
            <Icon name="chevron-right" size={14} />
          </button>
        ) : null}
      </div>

      <div
        className="chat-inspector__body"
        role="tabpanel"
        aria-label={tab === "telemetry" ? "Tool telemetry" : "Document preview"}
      >
        {tab === "telemetry" ? (
          <AgentInspector
            items={trace.items}
            pinnedId={pinnedId}
            onFollow={onFollow}
          />
        ) : (
          <ChatPreview target={previewTarget} />
        )}
      </div>
    </aside>
  );
}
