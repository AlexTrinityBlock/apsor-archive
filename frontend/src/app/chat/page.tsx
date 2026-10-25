import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../apis/fetch-client";
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
import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import { getActiveLocale, translate, translateApiErrorWithActiveLocale, useI18n } from "../i18n";
import {
  buildPersistedWorkTrace,
  mergeWorkTrace,
  type ResourceTarget,
} from "../agent/trace";
import { useMediaQuery } from "../agent/hook/useMediaQuery";
import { ApprovalStack } from "./component/ApprovalCard";
import { ChatComposer } from "./component/ChatComposer";
import { ChatHeader, type ChatPane } from "./component/ChatHeader";
import { ChatInspector, type InspectorTab } from "./component/ChatInspector";
import { ChatIntro } from "./component/ChatIntro";
import { ChatThread } from "./component/ChatThread";
import { ContextActions } from "./component/ContextActions";
import { ConversationRail } from "./component/ConversationRail";
import { MethodDisclosure } from "./component/MethodDisclosure";
import { RetryBar } from "./component/RetryBar";
import { StreamingTurn } from "./component/StreamingTurn";
import { useChatSplit } from "./hook/useChatSplit";
import { useChatStream } from "./hook/useChatStream";
import { buildMemoryTitles } from "./memory-titles";
import { invalidateConversation, invalidateConversationList } from "./query";
import {
  clearLastChatConversation,
  rememberLastChatConversation,
} from "./session-storage";
import {
  isRecord,
  mergeEntries,
  readRetryState,
  systemVersions,
  transcriptText,
  type CitationToken,
  type ResourceMeta,
} from "./types";
import { titleFromMessage } from "./format";
import "./chat.css";
import "../agent/agent.css";

const PAGE_SIZE = 200;
const NO_ENTRIES: readonly AgentEntrySchema[] = [];
const NARROW_QUERY = "(max-width: 899px)";

function parseConversationId(value: string | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return translateApiErrorWithActiveLocale(error, "chat.page.errorFallback");
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return translate(getActiveLocale(), "chat.page.errorFallback");
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
    <div className="empty-state chat-thread-state" role="status">
      <p className="mono-label">{eyebrow}</p>
      <h2 className="empty-state__title">{title}</h2>
      <p className="empty-state__description">{detail}</p>
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}

/** The persistent archive desk: sessions, stream, and inspector. */
// The page orchestrates conversation queries, streaming, approvals, and three
// coordinated panes; the complexity is in the composition, not a deep branch.
// eslint-disable-next-line sonarjs/cognitive-complexity
export function ChatPage() {
  const params = useParams<{ conversationId?: string }>();
  const conversationId = parseConversationId(params.conversationId);
  const invalidId =
    params.conversationId !== undefined && conversationId === null;
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const narrow = useMediaQuery(NARROW_QUERY);
  const { t, locale, formatNumber, formatRelative } = useI18n();
  const {
    containerRef,
    inspectorRef,
    ratio,
    collapsed,
    dragging,
    maxWidth,
    currentWidth,
    open: openInspector,
    setCollapsed,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerCancel,
    handleKeyDown,
  } = useChatSplit();

  const [drawerPreference, setDrawerPreference] = useState<boolean | null>(null);
  const drawerOpen = drawerPreference ?? !narrow;
  const setDrawerOpen = useCallback(
    (value: boolean | ((current: boolean) => boolean)) => {
      setDrawerPreference((preference) => {
        const current = preference ?? !narrow;
        return typeof value === "function" ? value(current) : value;
      });
    },
    [narrow],
  );
  const [pane, setPane] = useState<ChatPane>("thread");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("telemetry");
  const [previewTarget, setPreviewTarget] = useState<ResourceTarget | null>(null);
  const [pinnedId, setPinnedId] = useState<string | null>(null);
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
  const scrollRef = useRef<HTMLDivElement>(null);
  const extraInFlightRef = useRef(false);
  const stickToBottomRef = useRef(true);

  useScrollLock(narrow && drawerOpen);

  useEffect(() => {
    if (!narrow || !drawerOpen) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [drawerOpen, narrow, setDrawerOpen]);

  // Pins and previews belong to one conversation, so a route change resets
  // the inspector instead of carrying a stale selection across threads.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setPinnedId(null);
    setPreviewTarget(null);
    setInspectorTab("telemetry");
    setLastError(null);
    setPane("thread");
  }, [conversationId]);
  /* eslint-enable react-hooks/set-state-in-effect */

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

  // Persist only the route id; the transcript itself never touches storage.
  useEffect(() => {
    if (conversationId !== null) {
      rememberLastChatConversation(conversationId);
    }
  }, [conversationId]);

  // A missing conversation must not leave `/chat` redirecting back to it.
  useEffect(() => {
    if (
      conversationQuery.error instanceof ApiError &&
      conversationQuery.error.status === 404
    ) {
      clearLastChatConversation();
    }
  }, [conversationQuery.error]);

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

  const sendMessage = useCallback(
    (id: number, content: string) => {
      const trimmed = content.trim();
      if (trimmed.length === 0 || isStreaming) {
        return;
      }
      stickToBottomRef.current = true;
      setLastError(null);
      setPinnedId(null);
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
    setPinnedId(null);
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
  const memoryTitles = useMemo(
    () =>
      buildMemoryTitles(
        entries,
        (stream?.toolCalls ?? []).map((tool) => tool.data),
      ),
    [entries, stream?.toolCalls],
  );
  const transcript = useMemo(
    () => transcriptText(entries, locale),
    [entries, locale],
  );
  const retryState = useMemo(
    () =>
      readRetryState(
        entries,
        lastError ? { detail: lastError } : null,
        locale,
      ),
    [entries, lastError, locale],
  );
  const pendingApprovals = useMemo(
    () =>
      conversationId === null || approvalsQuery.data === undefined
        ? []
        : approvalsQuery.data.resources,
    [approvalsQuery.data, conversationId],
  );
  const waitingForApproval = pendingApprovals.length > 0;

  const persistedTrace = useMemo(
    () => buildPersistedWorkTrace(entries),
    [entries],
  );
  const trace = useMemo(
    () => mergeWorkTrace(persistedTrace, stream),
    [persistedTrace, stream],
  );

  const handleResolveApproval = useCallback(
    (approvalId: number, decision: "approve" | "reject") => {
      if (conversationId === null) {
        return Promise.resolve(false);
      }
      stickToBottomRef.current = true;
      setLastError(null);
      setPinnedId(null);
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
        toast.success(
          t("chat.page.forkToast", { entryId: formatNumber(entryId) }),
        );
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
      formatNumber,
      isStreaming,
      navigate,
      queryClient,
      t,
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
  const hiddenEntryCount = entries.reduce(
    (count, entry) => (entry.kind === "pi.system" ? count + 1 : count),
    0,
  );

  useEffect(() => {
    if (conversationId === null || !stickToBottomRef.current) {
      return;
    }
    const scroll = scrollRef.current;
    if (scroll) {
      scroll.scrollTop = scroll.scrollHeight;
    }
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
    setPinnedId(null);

    if (conversationId === null) {
      if (creating) {
        return;
      }
      setCreating(true);
      try {
        const created = await createConversation.mutateAsync({
          data: {
            title:
              titleFromMessage(trimmed) ||
              t("chat.page.newConversationTitle"),
          },
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
    setPinnedId(null);
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
    clearLastChatConversation();
    setDraft("");
    setLastError(null);
    setPinnedId(null);
    setPreviewTarget(null);
    setInspectorTab("telemetry");
    setPane("thread");
    if (narrow) {
      setDrawerOpen(false);
    }
    navigate("/chat");
  }, [navigate, narrow, setDraft, setDrawerOpen]);

  const handleNavigate = useCallback(() => {
    setPane("thread");
    if (narrow) {
      setDrawerOpen(false);
    }
  }, [narrow, setDrawerOpen]);

  const toggleDrawer = useCallback(() => {
    setDrawerOpen((value) => !value);
  }, [setDrawerOpen]);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
  }, [setDrawerOpen]);

  const retryConversations = useCallback(() => {
    void refetchConversations();
  }, [refetchConversations]);

  const revealInspector = useCallback(() => {
    openInspector();
    if (narrow) {
      setPane("inspector");
      setDrawerOpen(false);
    }
  }, [narrow, openInspector, setDrawerOpen]);

  const openFilePreview = useCallback(
    (fileId: number, chunk: number | null) => {
      setPreviewTarget({ type: "file", id: fileId, chunk, title: null });
      setInspectorTab("preview");
      revealInspector();
    },
    [revealInspector],
  );

  const handleOpenCitation = useCallback(
    (token: CitationToken) => {
      if (token.kind === "file") {
        openFilePreview(token.id, token.chunk);
        return;
      }
      if (token.kind === "memory") {
        navigate(`/memory/${token.id}`);
      }
    },
    [navigate, openFilePreview],
  );

  const handleOpenResource = useCallback(
    (resource: ResourceMeta) => {
      if (resource.resourceId === null) {
        return;
      }
      if (resource.resourceType === "file") {
        openFilePreview(resource.resourceId, resource.chunk);
        return;
      }
      navigate(`/memory/${resource.resourceId}`);
    },
    [navigate, openFilePreview],
  );

  const handleSelectTrace = useCallback(
    (traceId: string) => {
      setPinnedId(traceId);
      setInspectorTab("telemetry");
      revealInspector();
    },
    [revealInspector],
  );

  const handleFollow = useCallback(() => {
    setPinnedId(null);
  }, []);

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
          eyebrow={t("chat.page.invalidEyebrow")}
          title={t("chat.page.invalidTitle")}
          detail={t("chat.page.invalidDetail")}
          action={
            <ButtonLink
              to="/chat"
              variant="ink"
              size="sm"
              onClick={() => clearLastChatConversation()}
            >
              {t("chat.page.backToChat")}
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
          eyebrow={t("chat.page.loadingEyebrow")}
          title={t("chat.page.loadingTitle")}
          detail={t("chat.page.loadingDetail")}
        />
      );
    }
    if (conversationQuery.isError) {
      return (
        <ThreadState
          eyebrow={t("chat.page.errorEyebrow")}
          title={t("chat.page.errorTitle")}
          detail={describeError(conversationQuery.error)}
          action={
            <div className="chat-thread-state__actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void conversationQuery.refetch()}
              >
                {t("chat.page.tryAgain")}
              </Button>
              <ButtonLink
                to="/chat"
                variant="ink"
                size="sm"
                onClick={() => clearLastChatConversation()}
              >
                {t("chat.page.backToChat")}
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
          memoryTitles={memoryTitles}
          onForkEntry={handleForkEntry}
          forkingEntryId={forkingEntryId}
          forkDisabled={archived || isStreaming || forkingEntryId !== null}
          selectedTraceId={pinnedId}
          onSelectTrace={handleSelectTrace}
          onOpenCitation={handleOpenCitation}
          onOpenResource={handleOpenResource}
        />
        <ApprovalStack
          approvals={pendingApprovals}
          disabled={isStreaming}
          archived={archived}
          onResolve={handleResolveApproval}
        />
        {stream ? (
          <StreamingTurn
            stream={stream}
            memoryTitles={memoryTitles}
            selectedTraceId={pinnedId}
            onSelectTrace={handleSelectTrace}
            onOpenCitation={handleOpenCitation}
            onOpenResource={handleOpenResource}
          />
        ) : null}
        <MethodDisclosure
          conversation={conversation}
          hiddenCount={hiddenEntryCount}
          entryCount={conversation.entries_total}
          versions={systemVersions(entries)}
        />
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
                  <Loader size={14} label={t("chat.page.loadingMoreLabel")} />
                  {t("chat.page.loadingMore")}
                </>
              ) : (
                <>
                  {t("chat.page.loadMore")}
                  <Icon name="arrow-down" size={14} />
                </>
              )}
            </Button>
          </div>
        ) : null}
        {extraLoadError ? (
          <p className="chat-thread__more-error" role="alert">
            {t("chat.page.moreError")}{" "}
            <button type="button" onClick={() => void loadMore()}>
              {t("chat.page.moreErrorRetry")}
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
            <Icon name="archive" size={16} />
          </span>
          <div className="chat-archived__copy">
            <strong>{t("chat.page.archivedTitle")}</strong>
            <p>{t("chat.page.archivedDetail")}</p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void restoreThread()}
            disabled={restoring}
          >
            {restoring ? t("chat.page.restoring") : t("chat.page.restore")}
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

  const totalEntries = conversation?.entries_total ?? entries.length;
  const contextMeta = [
    t(
      totalEntries === 1 ? "chat.common.entryOne" : "chat.common.entryOther",
      { count: formatNumber(totalEntries) },
    ),
    waitingForApproval
      ? t("chat.page.awaitingApproval", {
          count: formatNumber(pendingApprovals.length),
        })
      : null,
    conversation?.last_entry_at
      ? t("chat.common.updatedAt", {
          time: formatRelative(conversation.last_entry_at),
        })
      : null,
  ].filter((item): item is string => item !== null);

  const streamPanel = (
    <section
      className="panel chat-stream-panel"
      aria-label={t("chat.page.streamAria")}
    >
      <div className="chat-stream__context">
        <span className="chat-stream__session">
          {conversationId === null
            ? t("chat.page.newSession")
            : t("chat.page.session", { id: conversationId })}
        </span>
        <span className="chat-stream__context-title">
          {conversation?.title ?? t("chat.page.defaultTitle")}
        </span>
        <span className="chat-stream__context-meta">
          {contextMeta.join(" · ")}
        </span>
      </div>

      <div
        className="chat-stream__scroll"
        ref={scrollRef}
        onScroll={(event) => {
          const element = event.currentTarget;
          stickToBottomRef.current =
            element.scrollHeight - element.scrollTop - element.clientHeight <
            140;
        }}
      >
        <div className="chat-stream__inner">
          {threadContent()}
          {lastError ? (
            <div className="chat-stream-error" role="alert">
              <Icon name="info" size={16} />
              <div>
                <strong>{t("chat.page.failureTitle")}</strong>
                <p>{lastError}</p>
              </div>
              <button
                type="button"
                className="chat-stream-error__close"
                onClick={() => setLastError(null)}
                aria-label={t("chat.page.dismissError")}
              >
                <Icon name="close" size={14} />
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="chat-composer-dock">{composer()}</div>
    </section>
  );

  const inspector = (
    <ChatInspector
      inspectorRef={inspectorRef}
      tab={inspectorTab}
      onTab={setInspectorTab}
      trace={trace}
      pinnedId={pinnedId}
      onFollow={handleFollow}
      previewTarget={previewTarget}
      onCollapse={() => setCollapsed(true)}
      narrow={narrow}
    />
  );

  return (
    <div className="chat-page">
      <ChatHeader
        conversation={conversation}
        conversationId={conversationId}
        transcript={transcript}
        archived={archived}
        drawerOpen={drawerOpen}
        narrow={narrow}
        pane={pane}
        inspectorCollapsed={collapsed}
        onToggleDrawer={toggleDrawer}
        onPane={setPane}
        onOpenInspector={openInspector}
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

      <div className="chat-workspace">
        <ConversationRail
          conversations={conversationsQuery.data?.resources ?? []}
          loading={conversationsQuery.isLoading}
          error={conversationsQuery.error}
          activeId={conversationId}
          open={drawerOpen}
          overlay={narrow}
          onRetry={retryConversations}
          onNew={startNewConversation}
          onClose={closeDrawer}
          onNavigate={handleNavigate}
        />

        <div className="chat-split" ref={containerRef} data-pane={pane}>
          {streamPanel}

          {!narrow ? (
            <div
              className={[
                "chat-resizer",
                dragging ? "is-dragging" : null,
                collapsed ? "is-collapsed" : null,
              ]
                .filter(Boolean)
                .join(" ")}
              role="separator"
              aria-orientation="vertical"
              aria-label={t("chat.page.resizerAria")}
              aria-valuemin={0}
              aria-valuemax={Math.round(maxWidth)}
              aria-valuenow={Math.round(currentWidth)}
              aria-valuetext={
                collapsed
                  ? t("chat.page.resizerCollapsed")
                  : t("chat.page.resizerWidth", {
                      width: formatNumber(Math.round(currentWidth)),
                    })
              }
              aria-controls="chat-inspector"
              tabIndex={0}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerCancel}
              onKeyDown={handleKeyDown}
              title={
                collapsed
                  ? t("chat.page.resizerOpen")
                  : t("chat.page.resizerResize")
              }
            >
              <span className="chat-resizer__line" aria-hidden="true" />
            </div>
          ) : null}

          {narrow || !collapsed ? (
            <div
              id="chat-inspector"
              className="chat-inspector-slot"
              style={{ flexBasis: `${ratio * 100}%` }}
            >
              {inspector}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
