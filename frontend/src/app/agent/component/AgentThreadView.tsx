import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import type {
  AgentConversationDetailSchema,
  AgentEntrySchema,
} from "../../generated-apis-types/schemas";
import { ChatThread } from "../../chat/component/ChatThread";
import { RetryBar } from "../../chat/component/RetryBar";
import { StreamingTurn } from "../../chat/component/StreamingTurn";
import type { ChatStreamView } from "../../chat/hook/useChatStream";
import type { RetryState } from "../../chat/types";

interface AgentThreadViewProps {
  readonly conversationId: number | null;
  readonly conversation: AgentConversationDetailSchema | null;
  readonly loading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly stream: ChatStreamView | null;
  readonly entries?: readonly AgentEntrySchema[];
  readonly hasMoreEntries?: boolean;
  readonly loadingMore?: boolean;
  readonly loadMoreError?: string | null;
  readonly onLoadMore?: () => void;
  readonly retryState?: RetryState;
  readonly retryDisabled?: boolean;
  readonly onRetryRun?: () => void;
}

function describeError(error: unknown): string {
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The conversation could not be read.";
}

function AgentIntro() {
  return (
    <div className="pi-agent-intro">
      <span className="pi-agent-intro__mark" aria-hidden="true">
        <Icon name="chat" size={22} />
      </span>
      <p className="eyebrow">A fresh sheet</p>
      <h3>Ask from this page.</h3>
      <p>
        The dock keeps one persistent transcript across the archive. The first
        note opens a thread; the current page is attached once as plain text.
      </p>
    </div>
  );
}

/**
 * The shared transcript body for the dock panel and expanded workspace.
 *
 * Controls and chrome live in the parents so the two surfaces stay visually
 * distinct while sharing the same transcript, streaming view, and states.
 */
export function AgentThreadView({
  conversationId,
  conversation,
  loading,
  error,
  onRetry,
  stream,
  entries,
  hasMoreEntries = false,
  loadingMore = false,
  loadMoreError = null,
  onLoadMore,
  retryState,
  retryDisabled = false,
  onRetryRun,
}: AgentThreadViewProps) {
  if (conversationId === null) {
    return <AgentIntro />;
  }
  if (loading && !conversation) {
    return (
      <div className="pi-agent-state" role="status">
        <Loader size={26} label="Opening the thread" />
        <p>Reading the sheets…</p>
      </div>
    );
  }
  if (error && !conversation) {
    return (
      <div className="pi-agent-state pi-agent-state--error" role="alert">
        <Icon name="info" size={18} />
        <p>{describeError(error)}</p>
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  }
  if (!conversation) {
    return null;
  }

  return (
    <>
      <ChatThread entries={entries ?? conversation.entries} conversation={conversation} />
      {stream ? <StreamingTurn stream={stream} /> : null}
      {retryState?.retryable && onRetryRun ? (
        <RetryBar
          state={retryState}
          disabled={retryDisabled}
          onRetry={onRetryRun}
        />
      ) : null}
      {hasMoreEntries && onLoadMore ? (
        <div className="pi-agent-more">
          <Button
            variant="secondary"
            size="sm"
            onClick={onLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? (
              <>
                <Loader size={14} label="Loading more entries" />
                Loading…
              </>
            ) : (
              <>
                Load more entries
                <Icon name="arrow-down" size={14} />
              </>
            )}
          </Button>
        </div>
      ) : null}
      {loadMoreError ? (
        <p className="pi-agent-more__error" role="alert">
          {loadMoreError}
        </p>
      ) : null}
    </>
  );
}
