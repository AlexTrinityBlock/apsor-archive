import { useId, useRef } from "react";

import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { ChatComposer } from "../../chat/component/ChatComposer";
import { useMediaQuery } from "../hook/useMediaQuery";
import { usePanelResize } from "../hook/usePanelResize";
import { AgentThreadControls } from "./AgentThreadControls";
import { AgentThreadView } from "./AgentThreadView";
import { PageContextBar } from "./PageContextBar";
import type { AgentDockSurfaceProps } from "./dock-types";

/**
 * The small bottom-right chat box.
 *
 * On narrow screens the CSS turns this same surface into a full-height sheet;
 * no separate mobile component means the thread and composer stay identical.
 */
export function AgentPanelSurface(props: AgentDockSurfaceProps) {
  const titleId = useId();
  const panelId = useId();
  const resizeHintId = useId();
  const panelRef = useRef<HTMLElement | null>(null);
  const sheet = useMediaQuery("(max-width: 640px)");
  const resizeEnabled = !sheet;
  const resize = usePanelResize(resizeEnabled, panelRef);
  const panelStyle =
    resizeEnabled
      ? {
          height: resize.height !== null ? `${resize.height}px` : undefined,
          minHeight: `${resize.minHeight}px`,
        }
      : undefined;
  const {
    archived,
    context,
    conversation,
    conversationError,
    conversationLoading,
    conversations,
    disabled,
    draft,
    endRef,
    entries,
    lastContextKey,
    lastError,
    listLoading,
    loadMoreError,
    loadingMore,
    hasMoreEntries,
    onLoadMore,
    retryState,
    retryDisabled,
    onRetryRun,
    onDismissError,
    onDraftChange,
    onContextApplied,
    onMode,
    onNewThread,
    onRetryThread,
    onScroll,
    onSelectThread,
    onStop,
    onSubmit,
    pending,
    scrollRef,
    selectedId,
    stream,
    streaming,
  } = props;
  const archivedThread = archived;

  return (
    <section
      id={panelId}
      ref={panelRef}
      className={["pi-agent-panel", resize.resizing ? "is-resizing" : null]
        .filter(Boolean)
        .join(" ")}
      style={panelStyle}
      role="dialog"
      aria-labelledby={titleId}
      tabIndex={-1}
    >
      {resizeEnabled ? (
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize agent panel height"
          aria-describedby={resizeHintId}
          aria-controls={panelId}
          aria-valuemin={resize.minHeight}
          aria-valuemax={resize.maxHeight}
          aria-valuenow={Math.round(resize.resolvedHeight)}
          aria-valuetext={`${Math.round(resize.resolvedHeight)} pixels`}
          tabIndex={0}
          className="pi-agent-panel__resize"
          data-agent-panel-resize
          {...resize.handleProps}
        >
          <span className="pi-agent-panel__resize-grip" aria-hidden="true" />
          <span id={resizeHintId} className="visually-hidden">
            Drag the top edge to resize, or press Arrow Up and Arrow Down. Home and End
            set the minimum and maximum height.
          </span>
        </div>
      ) : null}

      <header className="pi-agent-panel__head">
        <div className="pi-agent-panel__copy">
          <p className="eyebrow">Archive keeper · docked</p>
          <h2 id={titleId}>{conversation?.title ?? "New correspondence"}</h2>
        </div>
        <div className="pi-agent-panel__controls">
          <button
            type="button"
            className="pi-surface-button"
            onClick={() => onMode("collapsed")}
            aria-label="Collapse the agent to its seal"
            title="Collapse to seal"
          >
            <Icon name="chevron-down" size={16} />
          </button>
          <button
            type="button"
            className="pi-surface-button"
            onClick={() => onMode("expanded")}
            aria-label="Expand the agent workspace"
            title="Expand workspace"
          >
            <Icon name="layers" size={16} />
          </button>
          <button
            type="button"
            className="pi-surface-button pi-surface-button--close"
            onClick={() => onMode("collapsed")}
            aria-label="Close the agent panel"
            title="Close"
          >
            <Icon name="close" size={15} />
          </button>
        </div>
      </header>

      <AgentThreadControls
        conversations={conversations}
        selectedId={selectedId}
        loading={listLoading}
        streaming={streaming}
        archived={archivedThread}
        disabled={disabled || conversationLoading}
        onSelect={onSelectThread}
        onNew={onNewThread}
        onContextApplied={onContextApplied}
      />

      <div
        className="pi-agent-panel__scroll"
        ref={scrollRef}
        onScroll={onScroll}
      >
        <AgentThreadView
          conversationId={selectedId}
          conversation={conversation}
          loading={conversationLoading}
          error={conversationError}
          onRetry={onRetryThread}
          stream={stream}
          entries={entries}
          hasMoreEntries={hasMoreEntries}
          loadingMore={loadingMore}
          loadMoreError={loadMoreError}
          onLoadMore={onLoadMore}
          retryState={retryState}
          retryDisabled={retryDisabled}
          onRetryRun={onRetryRun}
        />
        <div ref={endRef} className="pi-agent-end" />
      </div>

      {lastError ? (
        <div className="chat-stream-error pi-agent-error" role="alert">
          <Icon name="info" size={16} />
          <div>
            <strong>That note could not be completed.</strong>
            <p>{lastError}</p>
          </div>
          <button
            type="button"
            className="chat-stream-error__close"
            onClick={onDismissError}
            aria-label="Dismiss error"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      ) : null}

      {archivedThread ? (
        <div className="pi-agent-archived">
          <Icon name="archive" size={15} />
          <p>This thread is archived. Restore it or open the full desk.</p>
          <ButtonLink
            to={selectedId === null ? "/chat" : `/chat/${selectedId}`}
            variant="ghost"
            size="sm"
          >
            Full desk
          </ButtonLink>
        </div>
      ) : null}

      <div className="pi-agent-panel__composer">
        <PageContextBar
          context={context}
          lastKey={lastContextKey}
          conversationId={selectedId}
        />
        <ChatComposer
          value={draft}
          onChange={onDraftChange}
          onSubmit={onSubmit}
          pending={pending}
          streaming={streaming}
          disabled={disabled || archivedThread}
          onStop={onStop}
        />
      </div>
    </section>
  );
}
