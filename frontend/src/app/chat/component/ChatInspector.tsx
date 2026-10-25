import type { RefObject } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { AgentInspector } from "../../agent/component/AgentInspector";
import {
  InspectorFileStage,
  InspectorMemoryStage,
} from "../../agent/component/inspector/common";
import { useI18n } from "../../i18n";
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
  const { t } = useI18n();
  return (
    <div className="empty-state chat-preview__empty">
      <span className="empty-state__icon" aria-hidden="true">
        <Icon name="file" size={20} />
      </span>
      <h2 className="empty-state__title">{t("chat.inspector.previewTitle")}</h2>
      <p className="empty-state__description">
        {t("chat.inspector.previewDetail")}
      </p>
    </div>
  );
}

function ChatPreview({ target }: { readonly target: ResourceTarget | null }) {
  const { t } = useI18n();
  if (!target) {
    return <PreviewEmpty />;
  }

  const isMemory = target.type === "memory";
  const openLabel = isMemory
    ? t("chat.inspector.openMemory")
    : t("chat.inspector.openInLibrary");
  let code = `memory:${target.id}`;
  if (!isMemory) {
    code = `file:${target.id}`;
    if (target.chunk !== null) {
      code += ` · ${t("chat.common.chunk", { chunk: target.chunk })}`;
    }
  }

  return (
    <div className="chat-preview">
      <header className="chat-preview__head">
        <div>
          <p className="mono-label">
            {isMemory
              ? t("chat.inspector.memoryPreview")
              : t("chat.inspector.documentPreview")}
          </p>
          <strong>
            {target.title ??
              t(
                isMemory
                  ? "chat.inspector.memoryFallback"
                  : "chat.inspector.fileFallback",
                { id: target.id },
              )}
          </strong>
          <code>{code}</code>
        </div>
        <Link className="text-link" to={viewerHref(target)}>
          {openLabel}
          <Icon name="arrow-up-right" size={12} />
        </Link>
      </header>
      <div className="chat-preview__scroll">
        {isMemory ? (
          <InspectorMemoryStage memoryId={target.id} />
        ) : (
          <InspectorFileStage fileId={target.id} chunk={target.chunk} />
        )}
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
  const { t } = useI18n();
  return (
    <aside
      ref={inspectorRef}
      className="panel chat-inspector"
      aria-label={t("chat.inspector.aria")}
    >
      <div className="chat-inspector__bar">
        <div
          className="tabs tabs--light chat-inspector__tabs"
          role="tablist"
          aria-label={t("chat.inspector.viewsAria")}
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === "telemetry"}
            className={tab === "telemetry" ? "tab is-active" : "tab"}
            onClick={() => onTab("telemetry")}
          >
            <Icon name="command" size={12} />
            {t("chat.inspector.telemetryTab")}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "preview"}
            className={tab === "preview" ? "tab is-active" : "tab"}
            onClick={() => onTab("preview")}
          >
            <Icon name="file" size={12} />
            {t("chat.inspector.previewTab")}
          </button>
        </div>
        {!narrow ? (
          <button
            type="button"
            className="chat-icon-btn chat-inspector__collapse"
            onClick={onCollapse}
            aria-label={t("chat.inspector.collapse")}
            title={t("chat.inspector.collapse")}
          >
            <Icon name="chevron-right" size={14} />
          </button>
        ) : null}
      </div>

      <div
        className="chat-inspector__body"
        role="tabpanel"
        aria-label={
          tab === "telemetry"
            ? t("chat.inspector.telemetryPanel")
            : t("chat.inspector.previewPanel")
        }
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
