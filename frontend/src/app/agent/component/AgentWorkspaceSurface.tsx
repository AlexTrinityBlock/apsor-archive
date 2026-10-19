import { useId } from "react";

import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { TreeMark } from "../../component/TreeMark";
import { ChatComposer } from "../../chat/component/ChatComposer";
import { AgentInspector } from "./AgentInspector";
import { AgentThreadControls } from "./AgentThreadControls";
import { AgentThreadView } from "./AgentThreadView";
import { PageContextBar } from "./PageContextBar";
import { WorkTrace } from "./WorkTrace";
import type { AgentDockSurfaceProps } from "./dock-types";

/**
 * The full-screen split workspace.
 *
 * It overlays the page instead of navigating, so the URL, scroll position, and
 * page snapshot behind the workspace stay exactly where the keeper left them.
 */
export function AgentWorkspaceSurface(props: AgentDockSurfaceProps) {
  const titleId = useId();
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
    onFollow,
    onMode,
    onNewThread,
    onPane,
    onPin,
    onRetryThread,
    onScroll,
    onSelectThread,
    onStop,
    onSubmit,
    pane,
    pending,
    pinnedId,
    scrollRef,
    selectedId,
    stream,
    streaming,
    trace,
  } = props;

  return (
    <div
      className="pi-agent-workspace"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
    >
      <header className="pi-agent-workspace__bar">
        <div className="pi-agent-workspace__brand">
          <span className="pi-agent-workspace__seal" aria-hidden="true">
            <TreeMark size={30} />
          </span>
          <div>
            <p className="eyebrow">Archive keeper · expanded</p>
            <h2 id={titleId}>{conversation?.title ?? "New correspondence"}</h2>
          </div>
        </div>

        <div className="pi-agent-workspace__actions">
          <div className="pi-pane-tabs" role="tablist" aria-label="Workspace panes">
            <button
              type="button"
              role="tab"
              aria-selected={pane === "thread"}
              className={pane === "thread" ? "pi-pane-tabs__button is-active" : "pi-pane-tabs__button"}
              onClick={() => onPane("thread")}
            >
              Correspondence
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pane === "inspector"}
              className={pane === "inspector" ? "pi-pane-tabs__button is-active" : "pi-pane-tabs__button"}
              onClick={() => onPane("inspector")}
            >
              Workbench
              {trace.items.length > 0 ? (
                <span className="pi-pane-tabs__count">{trace.items.length}</span>
              ) : null}
            </button>
          </div>

          <button
            type="button"
            className="pi-surface-button"
            onClick={() => onMode("panel")}
            aria-label="Return to the docked panel"
            title="Back to panel"
          >
            <Icon name="chevron-down" size={16} />
          </button>
          <button
            type="button"
            className="pi-surface-button pi-surface-button--close"
            onClick={() => onMode("collapsed")}
            aria-label="Collapse the agent workspace to its seal"
            title="Collapse to seal"
          >
            <Icon name="close" size={15} />
          </button>
        </div>
      </header>

      <div className="pi-agent-workspace__toolbar">
        <AgentThreadControls
          conversations={conversations}
          selectedId={selectedId}
          loading={listLoading}
          streaming={streaming}
          archived={archived}
          disabled={disabled || conversationLoading}
          onSelect={onSelectThread}
          onNew={onNewThread}
          onContextApplied={onContextApplied}
        />
        <span className="pi-agent-workspace__context">
          page context only moves when the page changes
        </span>
      </div>

      <div className="pi-agent-workspace__body" data-pane={pane}>
        <section className="pi-agent-workspace__thread" aria-label="Conversation">
          <WorkTrace
            items={trace.items}
            terminal={trace.terminal}
            pinnedId={pinnedId}
            onPin={onPin}
            streaming={stream !== null}
          />

          <div
            className="pi-agent-workspace__scroll"
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

          {archived ? (
            <div className="pi-agent-archived">
              <Icon name="archive" size={15} />
              <p>This thread is archived. Restore it from the full desk to write.</p>
              <ButtonLink
                to={selectedId === null ? "/chat" : `/chat/${selectedId}`}
                variant="ghost"
                size="sm"
              >
                Full desk
              </ButtonLink>
            </div>
          ) : null}

          <div className="pi-agent-workspace__composer">
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
              disabled={disabled || archived}
              onStop={onStop}
            />
          </div>
        </section>

        <div className="pi-agent-workspace__inspector">
          <AgentInspector
            items={trace.items}
            pinnedId={pinnedId}
            onFollow={onFollow}
          />
        </div>
      </div>
    </div>
  );
}
