import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../apis/fetch-client";
import { Badge } from "../component/Badge";
import { Button, ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { useToast } from "../component/Toast";
import { useScrollLock } from "../hook/useScrollLock";
import {
  listAgentEntries,
  useCreateAgentConversation,
  useForkAgentConversation,
  useGetAgentConversation,
  useListAgentApprovals,
  useListAgentConversations,
  useUpdateAgentConversation,
} from "../generated-apis-types/agent/agent";
import type {
  AgentConversationDetailSchema,
  AgentEntrySchema,
} from "../generated-apis-types/schemas";
import { formatRelative } from "../../lib/format";
import { ChatComposer } from "./component/ChatComposer";
import { ChatIntro } from "./component/ChatIntro";
import { ChatThread } from "./component/ChatThread";
import { ApprovalStack } from "./component/ApprovalCard";
import { ContextActions } from "./component/ContextActions";
import { ConversationRail } from "./component/ConversationRail";
import { RetryBar } from "./component/RetryBar";
import { StreamingTurn } from "./component/StreamingTurn";
import { useChatStream } from "./hook/useChatStream";
import { invalidateConversation, invalidateConversationList } from "./query";
import { isRecord, mergeEntries, readRetryState } from "./types";
import { titleFromMessage } from "./format";
import "./chat.css";

const PAGE_SIZE = 200;
const NO_ENTRIES: readonly AgentEntrySchema[] = [];

function parseConversationId(value: string | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The archive could not answer.";
}

function readRouteDraft(state: unknown): string | null {
  if (!isRecord(state)) {
    return null;
  }
  const draft = state.draft;
  return typeof draft === "string" && draft.trim().length > 0
    ? draft.trim()
    : null;
}

function ConversationHeader({
  conversation,
  archived,
  onOpenRail,
  onNew,
  contextActions,
}: {
  readonly conversation: AgentConversationDetailSchema | null;
  readonly archived: boolean;
  readonly onOpenRail: () => void;
  readonly onNew: () => void;
  readonly contextActions: ReactNode;
}) {
  const updated =
    conversation === null
      ? null
      : conversation.last_entry_at ?? conversation.created_at;

  return (
    <header className="chat-masthead">
      <div className="chat-masthead__copy">
        <p className="eyebrow">Studio · correspondence desk</p>
        <h1>{conversation?.title ?? "Correspondence desk"}</h1>
        <p className="chat-masthead__meta">
          {conversation ? (
            <>
              <span>{conversation.provider}</span>
              <span aria-hidden="true">·</span>
              <span>{conversation.model}</span>
              <span aria-hidden="true">·</span>
              <span>{conversation.entries_total} entries</span>
              {updated ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span>updated {formatRelative(updated)}</span>
                </>
              ) : null}
              {conversation.parent_conversation_id !== null ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="chat-masthead__fork">
                    Forked from{" "}
                    <Link
                      to={`/chat/${conversation.parent_conversation_id}`}
                    >
                      #{conversation.parent_conversation_id}
                    </Link>
                    {conversation.fork_at_entry_id !== null ? (
                      <span> at entry {conversation.fork_at_entry_id}</span>
                    ) : null}
                  </span>
                </>
              ) : null}
              {archived ? <Badge tone="ochre">Archived</Badge> : null}
            </>
          ) : (
            <span>Persistent transcripts · citations · resource cards</span>
          )}
        </p>
      </div>
      <div className="chat-masthead__actions">
        <Button
          variant="secondary"
          size="sm"
          className="chat-rail-toggle"
          onClick={onOpenRail}
          aria-controls="chat-thread-rail"
        >
          <Icon name="menu" size={15} />
          Threads
        </Button>
        <Button variant="primary" size="sm" onClick={onNew}>
          <Icon name="plus" size={14} />
          New
        </Button>
        {contextActions}
      </div>
    </header>
  );
}

function ThreadState({
  eyebrow,
  title,
  detail,
  action,
}: {
  readonly eyebrow: string;
  readonly title: string;
  readonly detail: string;
  readonly action?: ReactNode;
}) {
  return (
    <div className="chat-thread-state" role="status">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{detail}</p>
      {action ? <div className="chat-thread-state__action">{action}</div> : null}
    </div>
  );
}

/** The persistent reading room for the Pi-shaped entry log. */
export function ChatPage() {
  const params = useParams<{ conversationId?: string }>();
  const conversationId = parseConversationId(params.conversationId);
  const invalidId =
    params.conversationId !== undefined && conversationId === null;
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const [railOpen, setRailOpen] = useState(false);
  const [draftState, setDraftState] = useState<{
    readonly id: number | null;
    readonly value: string;
  }>({ id: conversationId, value: "" });
  const draft = draftState.id === conversationId ? draftState.value : "";
  const setDraft = useCallback(
    (value: string) => {
      setDraftState({ id: conversationId, value });
    },
    [conversationId],
  );
  const [lastError, setLastError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [extraStateId, setExtraStateId] = useState<number | null>(null);
  const [extraEntries, setExtraEntries] = useState<AgentEntrySchema[]>([]);
  const [extraCursor, setExtraCursor] = useState<number | null>(null);
  const [extraHasMore, setExtraHasMore] = useState(false);
  const [extraLoaded, setExtraLoaded] = useState(false);
  const [extraLoading, setExtraLoading] = useState(false);
  const [extraError, setExtraError] = useState<string | null>(null);
  const handledRouteDraft = useRef<string | null>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const extraInFlightRef = useRef(false);
  const stickToBottomRef = useRef(true);

  useScrollLock(railOpen);

  const conversationsQuery = useListAgentConversations({ limit: 100 });
  const refetchConversations = conversationsQuery.refetch;
  const conversationQuery = useGetAgentConversation(
    conversationId ?? 0,
    { limit: PAGE_SIZE },
    {
      query: {
        enabled: conversationId !== null,
        retry: false,
      },
    },
  );
  const approvalsQuery = useListAgentApprovals(
    conversationId ?? 0,
    { status: "pending" },
    {
      query: {
        enabled: conversationId !== null,
        retry: false,
      },
    },
  );
  const createConversation = useCreateAgentConversation();
  const updateConversation = useUpdateAgentConversation();
  const forkConversation = useForkAgentConversation();
  const toast = useToast();
  const [forkingEntryId, setForkingEntryId] = useState<number | null>(null);

  const handleStreamError = useCallback((message: string) => {
    stickToBottomRef.current = true;
    setLastError(message);
  }, []);
  const { stream, isStreaming, start, retry, resolveApproval, stop } =
    useChatStream(handleStreamError);

  // Abort any open run when the selected thread changes or the page unmounts.
  useEffect(() => {
    stickToBottomRef.current = true;
    return () => stop();
  }, [conversationId, stop]);

  useEffect(() => {
    const handleScroll = () => {
      const remaining =
        document.documentElement.scrollHeight -
        window.scrollY -
        window.innerHeight;
      stickToBottomRef.current = remaining < 160;
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!railOpen) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setRailOpen(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [railOpen]);

  const sendMessage = useCallback(
    (id: number, content: string) => {
      const trimmed = content.trim();
      if (trimmed.length === 0 || isStreaming) {
        return;
      }
      stickToBottomRef.current = true;
      setLastError(null);
      setDraft("");
      void start(id, trimmed);
    },
    [isStreaming, setDraft, start],
  );

  useEffect(() => {
    if (conversationId === null) {
      return;
    }
    const routeDraft = readRouteDraft(location.state);
    if (!routeDraft) {
      return;
    }
    const key = `${conversationId}:${routeDraft}`;
    if (handledRouteDraft.current === key) {
      return;
    }
    handledRouteDraft.current = key;
    navigate(location.pathname, { replace: true, state: null });
    setLastError(null);
    setDraft("");
    void start(conversationId, routeDraft);
  }, [
    conversationId,
    location.pathname,
    location.state,
    navigate,
    setDraft,
    start,
  ]);

  const conversation = conversationQuery.data ?? null;
  const archived = conversation?.status === "archived";
  const baseEntries = conversation?.entries ?? NO_ENTRIES;
  const extraForCurrent = extraStateId === conversationId;
  const currentExtraEntries = extraForCurrent ? extraEntries : NO_ENTRIES;
  const entries = useMemo(
    () => mergeEntries(baseEntries, currentExtraEntries),
    [baseEntries, currentExtraEntries],
  );
  const retryState = useMemo(
    () => readRetryState(entries, lastError ? { detail: lastError } : null),
    [entries, lastError],
  );
  const pendingApprovals = useMemo(
    () =>
      conversationId === null || approvalsQuery.data === undefined
        ? []
        : approvalsQuery.data.resources,
    [approvalsQuery.data, conversationId],
  );
  const waitingForApproval = pendingApprovals.length > 0;
  const handleResolveApproval = useCallback(
    (approvalId: number, decision: "approve" | "reject") => {
      if (conversationId === null) {
        return Promise.resolve(false);
      }
      stickToBottomRef.current = true;
      setLastError(null);
      return resolveApproval(conversationId, approvalId, decision);
    },
    [conversationId, resolveApproval],
  );

  const forkAtEntry = useCallback(
    async (entryId: number) => {
      if (
        conversationId === null ||
        archived ||
        isStreaming ||
        forkingEntryId !== null
      ) {
        return;
      }
      setForkingEntryId(entryId);
      try {
        const forked = await forkConversation.mutateAsync({
          conversationId,
          data: { at_entry_id: entryId },
        });
        await invalidateConversationList(queryClient);
        toast.success(`Forked from entry ${entryId}.`);
        navigate(`/chat/${forked.id}`);
      } catch (error) {
        toast.error(describeError(error));
      } finally {
        setForkingEntryId(null);
      }
    },
    [
      archived,
      conversationId,
      forkConversation,
      forkingEntryId,
      isStreaming,
      navigate,
      queryClient,
      toast,
    ],
  );
  const handleForkEntry = useCallback(
    (entryId: number) => {
      void forkAtEntry(entryId);
    },
    [forkAtEntry],
  );

  const applyContextBoundary = useCallback(
    (entry: AgentEntrySchema) => {
      if (conversationId === null) {
        return;
      }
      setExtraStateId(conversationId);
      if (extraForCurrent && extraLoaded) {
        setExtraEntries((current) => mergeEntries(current, [entry]));
        return;
      }
      setExtraEntries([entry]);
      setExtraCursor(conversation?.entries_next_after_id ?? null);
      setExtraHasMore(conversation?.entries_has_more ?? false);
      setExtraLoaded(true);
    },
    [conversation, conversationId, extraForCurrent, extraLoaded],
  );

  const hasMore =
    extraForCurrent && extraLoaded
      ? extraHasMore
      : (conversation?.entries_has_more ?? false);
  const nextAfterId =
    extraForCurrent && extraLoaded
      ? extraCursor
      : (conversation?.entries_next_after_id ?? null);
  const loadingMore = extraForCurrent && extraLoading;
  const extraLoadError = extraForCurrent ? extraError : null;
  const streamToolCount = stream?.toolCalls.length ?? 0;
  const streamTextLength = stream?.assistantText.length ?? 0;
  const streamingActive = stream !== null;

  useEffect(() => {
    if (conversationId === null || !stickToBottomRef.current) {
      return;
    }
    threadEndRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  }, [
    conversationId,
    entries.length,
    lastError,
    pendingApprovals.length,
    streamingActive,
    streamTextLength,
    streamToolCount,
  ]);

  const submit = async (value: string) => {
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      return;
    }
    setLastError(null);

    if (conversationId === null) {
      if (creating) {
        return;
      }
      setCreating(true);
      try {
        const created = await createConversation.mutateAsync({
          data: { title: titleFromMessage(trimmed) },
        });
        await invalidateConversationList(queryClient);
        setDraft("");
        navigate(`/chat/${created.id}`, {
          replace: true,
          state: { draft: trimmed },
        });
      } catch (error) {
        setLastError(describeError(error));
      } finally {
        setCreating(false);
      }
      return;
    }

    sendMessage(conversationId, trimmed);
  };

  const handleRetryRun = useCallback(() => {
    if (conversationId === null || !retryState.retryable) {
      return;
    }
    stickToBottomRef.current = true;
    setLastError(null);
    void retry(conversationId, retryState.lastUserText);
  }, [conversationId, retry, retryState.lastUserText, retryState.retryable]);

  const loadMore = async () => {
    if (
      conversationId === null ||
      nextAfterId === null ||
      extraInFlightRef.current
    ) {
      return;
    }
    extraInFlightRef.current = true;
    setExtraStateId(conversationId);
    setExtraLoading(true);
    setExtraError(null);
    try {
      const page = await listAgentEntries(conversationId, {
        after_id: nextAfterId,
        limit: PAGE_SIZE,
      });
      setExtraEntries((current) =>
        mergeEntries(extraForCurrent && extraLoaded ? current : [], page.entries),
      );
      setExtraCursor(page.next_after_id);
      setExtraHasMore(page.has_more);
      setExtraLoaded(true);
    } catch (error) {
      setExtraError(describeError(error));
    } finally {
      extraInFlightRef.current = false;
      setExtraLoading(false);
    }
  };

  const startNewConversation = useCallback(() => {
    setDraft("");
    setLastError(null);
    navigate("/chat");
    setRailOpen(false);
  }, [navigate, setDraft]);

  const openRail = useCallback(() => setRailOpen(true), []);
  const closeRail = useCallback(() => setRailOpen(false), []);
  const retryConversations = useCallback(() => {
    void refetchConversations();
  }, [refetchConversations]);

  const restoreThread = async () => {
    if (conversationId === null || restoring) {
      return;
    }
    setRestoring(true);
    try {
      await updateConversation.mutateAsync({
        conversationId,
        data: { status: "active" },
      });
      await invalidateConversation(queryClient, conversationId);
      setLastError(null);
    } catch (error) {
      setLastError(describeError(error));
    } finally {
      setRestoring(false);
    }
  };

  const threadContent = () => {
    if (invalidId) {
      return (
        <ThreadState
          eyebrow="Address not found"
          title="That thread address is not valid."
          detail="Thread addresses are positive integers. The desk is still open."
          action={
            <ButtonLink to="/chat" variant="ink" size="sm">
              Back to the desk
            </ButtonLink>
          }
        />
      );
    }
    if (conversationId === null) {
      return (
        <ChatIntro
          onSuggestion={(text) => setDraft(text)}
          disabled={creating}
        />
      );
    }
    if (conversationQuery.isLoading) {
      return (
        <ThreadState
          eyebrow="Opening the thread"
          title="Reading the sheets…"
          detail="The transcript and its method are being fetched from the archive."
        />
      );
    }
    if (conversationQuery.isError) {
      return (
        <ThreadState
          eyebrow="Read interrupted"
          title="This thread could not be opened."
          detail={describeError(conversationQuery.error)}
          action={
            <div className="chat-thread-state__actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void conversationQuery.refetch()}
              >
                Try again
              </Button>
              <ButtonLink to="/chat" variant="ink" size="sm">
                Back to the desk
              </ButtonLink>
            </div>
          }
        />
      );
    }
    if (!conversation) {
      return null;
    }

    return (
      <>
        <ChatThread
          entries={entries}
          conversation={conversation}
          onForkEntry={handleForkEntry}
          forkingEntryId={forkingEntryId}
          forkDisabled={archived || isStreaming || forkingEntryId !== null}
        />
        <ApprovalStack
          approvals={pendingApprovals}
          disabled={isStreaming}
          archived={archived}
          onResolve={handleResolveApproval}
        />
        {stream ? <StreamingTurn stream={stream} /> : null}
        {hasMore ? (
          <div className="chat-thread__more">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void loadMore()}
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
        {extraLoadError ? (
          <p className="chat-thread__more-error" role="alert">
            More entries could not be read.{" "}
            <button type="button" onClick={() => void loadMore()}>
              Try again
            </button>
          </p>
        ) : null}
      </>
    );
  };

  const composer = () => {
    if (invalidId) {
      return null;
    }
    if (archived) {
      return (
        <div className="chat-archived">
          <span className="chat-archived__mark" aria-hidden="true">
            <Icon name="archive" size={18} />
          </span>
          <div className="chat-archived__copy">
            <strong>This thread is archived.</strong>
            <p>Restore it to write another note. Every entry stays readable.</p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void restoreThread()}
            disabled={restoring}
          >
            {restoring ? "Restoring…" : "Restore thread"}
          </Button>
        </div>
      );
    }

    return (
      <>
        {retryState.retryable ? (
          <RetryBar
            state={retryState}
            disabled={
              isStreaming ||
              creating ||
              (conversationId !== null && conversationQuery.isError)
            }
            onRetry={handleRetryRun}
          />
        ) : null}
        <ChatComposer
          value={draft}
          onChange={setDraft}
          onSubmit={(value) => void submit(value)}
          pending={creating || isStreaming}
          streaming={isStreaming}
          disabled={
            creating ||
            waitingForApproval ||
            (conversationId !== null && conversationQuery.isError)
          }
          onStop={stop}
        />
      </>
    );
  };

  return (
    <div className="page chat-page">
      <ConversationHeader
        conversation={conversation}
        archived={archived}
        onOpenRail={openRail}
        onNew={startNewConversation}
        contextActions={
          <ContextActions
            key={`${conversationId ?? "new"}:${archived ? "archived" : "active"}`}
            conversationId={conversationId}
            streaming={isStreaming}
            archived={archived}
            disabled={
              conversationId !== null &&
              (conversationQuery.isLoading ||
                conversationQuery.isError ||
                waitingForApproval)
            }
            onApplied={applyContextBoundary}
          />
        }
      />

      <div className="chat-room">
        <ConversationRail
          key={conversationId ?? "new"}
          conversations={conversationsQuery.data?.resources ?? []}
          loading={conversationsQuery.isLoading}
          error={conversationsQuery.error}
          activeId={conversationId}
          open={railOpen}
          onRetry={retryConversations}
          onNew={startNewConversation}
          onClose={closeRail}
        />

        <div className="chat-main">
          {threadContent()}

          {lastError ? (
            <div className="chat-stream-error" role="alert">
              <Icon name="info" size={16} />
              <div>
                <strong>That note could not be completed.</strong>
                <p>{lastError}</p>
              </div>
              <button
                type="button"
                className="chat-stream-error__close"
                onClick={() => setLastError(null)}
                aria-label="Dismiss error"
              >
                <Icon name="close" size={14} />
              </button>
            </div>
          ) : null}

          <div className="chat-thread__end" ref={threadEndRef} />
          {composer()}
        </div>
      </div>
    </div>
  );
}
