import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useScrollLock } from "../hook/useScrollLock";
import {
  listAgentEntries,
  useCreateAgentConversation,
  useGetAgentConversation,
  useListAgentConversations,
} from "../generated-apis-types/agent/agent";
import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import { TreeMark } from "../component/TreeMark";
import { invalidateConversationList } from "../chat/query";
import {
  lastPageContextKey,
  mergeEntries,
  readRetryState,
} from "../chat/types";
import { titleFromMessage } from "../chat/format";
import { useChatStream } from "../chat/hook/useChatStream";
import { usePageContext } from "./hook/usePageContext";
import { useMediaQuery } from "./hook/useMediaQuery";
import { buildPersistedWorkTrace, mergeWorkTrace } from "./trace";
import { readPageContextEntry } from "./page-context";
import { AgentPanelSurface } from "./component/AgentPanelSurface";
import { AgentWorkspaceSurface } from "./component/AgentWorkspaceSurface";
import type {
  AgentDockMode,
  AgentDockSurfaceProps,
  AgentPane,
} from "./component/dock-types";
import "./agent.css";

const MODE_KEY = "dendromatrix.agentDock.mode";
const CONVERSATION_KEY = "dendromatrix.agentDock.conversation";
const NO_ENTRIES: readonly AgentEntrySchema[] = [];

function readMode(): AgentDockMode {
  try {
    const value = window.localStorage.getItem(MODE_KEY);
    if (value === "collapsed" || value === "panel" || value === "expanded") {
      return value;
    }
  } catch {
    // Private browsing can reject storage reads; the default is harmless.
  }
  return "collapsed";
}

function storeMode(mode: AgentDockMode): void {
  try {
    window.localStorage.setItem(MODE_KEY, mode);
  } catch {
    // The dock still works for this session.
  }
}

function readConversationId(): number | null {
  try {
    const raw = window.localStorage.getItem(CONVERSATION_KEY);
    if (!raw || !/^\d+$/.test(raw)) {
      return null;
    }
    const value = Number(raw);
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function storeConversationId(id: number | null): void {
  try {
    if (id === null) {
      window.localStorage.removeItem(CONVERSATION_KEY);
    } else {
      window.localStorage.setItem(CONVERSATION_KEY, String(id));
    }
  } catch {
    // Selection still survives navigation in memory.
  }
}

function lastEntryContextKey(entries: readonly AgentEntrySchema[]): string | null {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const context = readPageContextEntry(entries[index]);
    if (context) {
      return context.key;
    }
  }
  return null;
}

function describeError(error: unknown): string {
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The archive agent could not answer.";
}

/** The global three-state agent dock, mounted by `AppShell` outside `main`. */
export function AgentDock() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<AgentDockMode>(readMode);
  const [selectedId, setSelectedId] = useState<number | null>(readConversationId);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const [pane, setPane] = useState<AgentPane>("thread");
  const [localContextKeys, setLocalContextKeys] = useState<Record<number, string>>({});
  const [extraFor, setExtraFor] = useState<number | null>(null);
  const [extraEntries, setExtraEntries] = useState<AgentEntrySchema[]>([]);
  const [extraCursor, setExtraCursor] = useState<number | null>(null);
  const [extraHasMore, setExtraHasMore] = useState(false);
  const [extraLoaded, setExtraLoaded] = useState(false);
  const [extraLoading, setExtraLoading] = useState(false);
  const [extraError, setExtraError] = useState<string | null>(null);
  const sentContextRef = useRef<{
    readonly conversationId: number;
    readonly key: string;
  } | null>(null);
  const extraInFlightRef = useRef(false);
  const autoRefreshRef = useRef<number | null>(null);
  const streamEndedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const stickRef = useRef(true);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const wasCollapsedRef = useRef(mode === "collapsed");

  const narrow = useMediaQuery("(max-width: 860px)");
  const sheet = useMediaQuery("(max-width: 640px)");
  const context = usePageContext(mode !== "collapsed");
  const conversationsQuery = useListAgentConversations(
    { limit: 100 },
    { query: { enabled: mode !== "collapsed" } },
  );
  const conversationQuery = useGetAgentConversation(
    selectedId ?? 0,
    { limit: 200 },
    { query: { enabled: mode !== "collapsed" && selectedId !== null, retry: false } },
  );
  const createConversation = useCreateAgentConversation();

  const handleStreamError = useCallback((message: string) => {
    stickRef.current = true;
    setLastError(message);
  }, []);
  const { stream, isStreaming, start, retry, stop } = useChatStream(handleStreamError);
  const activeStream = stream?.conversationId === selectedId ? stream : null;

  const conversation = conversationQuery.data ?? null;
  const baseEntries = conversation?.entries ?? NO_ENTRIES;
  const extraForCurrent = extraFor === selectedId;
  const visibleExtraEntries = extraForCurrent ? extraEntries : NO_ENTRIES;
  const entries = useMemo(
    () => mergeEntries(baseEntries, visibleExtraEntries),
    [baseEntries, visibleExtraEntries],
  );
  const hasMoreEntries =
    extraForCurrent && extraLoaded
      ? extraHasMore
      : (conversation?.entries_has_more ?? false);
  const nextAfterId =
    extraForCurrent && extraLoaded
      ? extraCursor
      : (conversation?.entries_next_after_id ?? null);
  const loadingMore = extraForCurrent && extraLoading;
  const loadMoreError = extraForCurrent ? extraError : null;
  const archived = conversation?.status === "archived";
  const lastContextKey = useMemo(() => {
    if (selectedId === null) {
      return null;
    }
    const local = localContextKeys[selectedId] ?? null;
    const persisted =
      lastPageContextKey(conversation) ?? lastEntryContextKey(entries);
    return activeStream === null ? (persisted ?? local) : (local ?? persisted);
  }, [activeStream, conversation, entries, localContextKeys, selectedId]);
  const persistedTrace = useMemo(() => buildPersistedWorkTrace(entries), [entries]);
  const trace = useMemo(
    () => mergeWorkTrace(persistedTrace, activeStream),
    [activeStream, persistedTrace],
  );
  const retryState = useMemo(
    () => readRetryState(entries, lastError ? { detail: lastError } : null),
    [entries, lastError],
  );

  useScrollLock(mode === "expanded" || (mode === "panel" && sheet));

  useEffect(() => {
    storeMode(mode);
  }, [mode]);

  useEffect(() => {
    storeConversationId(selectedId);
  }, [selectedId]);

  useEffect(() => {
    const runId = stream?.runId ?? null;
    if (runId === null || selectedId === null) {
      return;
    }
    const sent = sentContextRef.current;
    if (!sent || sent.conversationId !== selectedId) {
      return;
    }
    sentContextRef.current = null;
    setLocalContextKeys((current) =>
      current[sent.conversationId] === sent.key
        ? current
        : { ...current, [sent.conversationId]: sent.key },
    );
  }, [selectedId, stream?.runId]);

  useEffect(() => {
    if (!stickRef.current) {
      return;
    }
    const node = scrollRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [
    entries.length,
    lastError,
    selectedId,
    stream?.assistantText.length,
    stream?.toolCalls.length,
  ]);

  useEffect(() => {
    if (mode === "collapsed") {
      if (!wasCollapsedRef.current) {
        previousFocusRef.current?.focus();
      }
      wasCollapsedRef.current = true;
      return;
    }
    if (wasCollapsedRef.current) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
    }
    wasCollapsedRef.current = false;
    const timer = window.setTimeout(() => {
      const surface = document.querySelector<HTMLElement>(
        ".pi-agent-panel, .pi-agent-workspace",
      );
      surface?.focus();
    }, 20);
    return () => window.clearTimeout(timer);
  }, [mode]);

  useEffect(() => {
    if (mode === "collapsed") {
      return;
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) {
        return;
      }
      const tag = (event.target as HTMLElement | null)?.tagName ?? "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return;
      }
      event.preventDefault();
      setMode(mode === "expanded" ? "panel" : "collapsed");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [mode]);

  const resetExtraEntries = () => {
    autoRefreshRef.current = null;
    setExtraFor(null);
    setExtraEntries([]);
    setExtraCursor(null);
    setExtraHasMore(false);
    setExtraLoaded(false);
    setExtraError(null);
  };

  const refreshAllExtra = useCallback(
    async (conversationId: number, afterId: number) => {
      setExtraFor(conversationId);
      setExtraLoading(true);
      setExtraError(null);
      const collected: AgentEntrySchema[] = [];
      let cursor: number | null = afterId;
      let pages = 0;
      try {
        while (cursor !== null && pages < 10) {
          const page = await listAgentEntries(conversationId, {
            after_id: cursor,
            limit: 200,
          });
          collected.push(...page.entries);
          cursor = page.next_after_id;
          pages += 1;
          if (!page.has_more) {
            break;
          }
        }
        setExtraEntries(collected);
        setExtraCursor(cursor);
        setExtraHasMore(cursor !== null);
        setExtraLoaded(true);
      } catch (error) {
        setExtraError(describeError(error));
      } finally {
        setExtraLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (isStreaming) {
      streamEndedRef.current = true;
      return;
    }
    if (!streamEndedRef.current || selectedId === null) {
      return;
    }
    streamEndedRef.current = false;
    autoRefreshRef.current = selectedId;
    const cursor = conversationQuery.data?.entries_next_after_id ?? null;
    if (cursor === null) {
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshAllExtra(selectedId, cursor);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [conversationQuery.data?.entries_next_after_id, isStreaming, refreshAllExtra, selectedId]);

  useEffect(() => {
    if (mode === "collapsed" || selectedId === null) {
      return;
    }
    const cursor = conversationQuery.data?.entries_next_after_id ?? null;
    if (cursor === null || autoRefreshRef.current === selectedId) {
      return;
    }
    autoRefreshRef.current = selectedId;
    const timer = window.setTimeout(() => {
      void refreshAllExtra(selectedId, cursor);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [conversationQuery.data?.entries_next_after_id, mode, refreshAllExtra, selectedId]);

  const loadMore = async () => {
    if (selectedId === null || nextAfterId === null || extraInFlightRef.current) {
      return;
    }
    extraInFlightRef.current = true;
    setExtraFor(selectedId);
    setExtraLoading(true);
    setExtraError(null);
    try {
      const page = await listAgentEntries(selectedId, {
        after_id: nextAfterId,
        limit: 200,
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

  const selectThread = useCallback(
    (id: number | null) => {
      if (isStreaming) {
        stop();
      }
      stickRef.current = true;
      setLastError(null);
      setDraft("");
      setPinnedId(null);
      setPane("thread");
      resetExtraEntries();
      setSelectedId(id);
    },
    [isStreaming, stop],
  );

  const newThread = useCallback(() => {
    if (isStreaming) {
      stop();
    }
    stickRef.current = true;
    setLastError(null);
    setDraft("");
    setPinnedId(null);
    setPane("thread");
    resetExtraEntries();
    setSelectedId(null);
  }, [isStreaming, stop]);

  const submit = async (value: string) => {
    const trimmed = value.trim();
    if (trimmed.length === 0 || creating || isStreaming || archived) {
      return;
    }
    setLastError(null);
    setDraft("");
    const pageContext = context
      ? {
          key: context.key,
          path: context.path,
          title: context.title,
          text: context.text,
        }
      : undefined;
    if (selectedId !== null) {
      sentContextRef.current = pageContext
        ? { conversationId: selectedId, key: pageContext.key }
        : null;
      stickRef.current = true;
      void start(selectedId, trimmed, pageContext);
      return;
    }

    if (creating) {
      return;
    }
    setCreating(true);
    try {
      const created = await createConversation.mutateAsync({
        data: { title: titleFromMessage(trimmed) },
      });
      await invalidateConversationList(queryClient);
      sentContextRef.current = pageContext
        ? { conversationId: created.id, key: pageContext.key }
        : null;
      stickRef.current = true;
      setPinnedId(null);
      setPane("thread");
      resetExtraEntries();
      setSelectedId(created.id);
      void start(created.id, trimmed, pageContext);
    } catch (error) {
      sentContextRef.current = null;
      setDraft(value);
      setLastError(describeError(error));
    } finally {
      setCreating(false);
    }
  };

  const handleScroll = () => {
    const node = scrollRef.current;
    if (!node) {
      return;
    }
    stickRef.current =
      node.scrollHeight - node.scrollTop - node.clientHeight < 120;
  };

  const pin = useCallback(
    (id: string) => {
      setPinnedId(id);
      if (narrow) {
        setPane("inspector");
      }
    },
    [narrow],
  );

  const follow = useCallback(() => {
    setPinnedId(null);
  }, []);

  const retryRun = useCallback(() => {
    if (selectedId === null || !retryState.retryable) {
      return;
    }
    stickRef.current = true;
    setLastError(null);
    void retry(selectedId, retryState.lastUserText);
  }, [retry, retryState.lastUserText, retryState.retryable, selectedId]);

  const applyContextBoundary = useCallback(
    (entry: AgentEntrySchema) => {
      if (selectedId === null) {
        return;
      }
      setExtraFor(selectedId);
      setExtraError(null);
      if (extraForCurrent && extraLoaded) {
        setExtraEntries((current) => mergeEntries(current, [entry]));
        return;
      }
      setExtraEntries([entry]);
      setExtraCursor(conversation?.entries_next_after_id ?? null);
      setExtraHasMore(conversation?.entries_has_more ?? false);
      setExtraLoaded(true);
    },
    [conversation, extraForCurrent, extraLoaded, selectedId],
  );

  const surfaceProps: AgentDockSurfaceProps = {
    conversations: conversationsQuery.data?.resources ?? [],
    listLoading: conversationsQuery.isLoading,
    selectedId,
    conversation,
    conversationLoading: conversationQuery.isLoading,
    conversationError: conversationQuery.error,
    entries,
    stream: activeStream,
    context,
    lastContextKey,
    draft,
    onDraftChange: setDraft,
    onSubmit: (value) => void submit(value),
    pending: creating || isStreaming,
    streaming: activeStream !== null,
    disabled:
      creating ||
      isStreaming ||
      archived ||
      (selectedId !== null && conversationQuery.isError),
    onStop: stop,
    archived,
    lastError,
    onDismissError: () => setLastError(null),
    onSelectThread: selectThread,
    onNewThread: newThread,
    onRetryThread: () => void conversationQuery.refetch(),
    hasMoreEntries,
    loadingMore,
    loadMoreError,
    onLoadMore: () => void loadMore(),
    retryState,
    retryDisabled: isStreaming || creating || archived,
    onRetryRun: retryRun,
    onContextApplied: applyContextBoundary,
    scrollRef,
    endRef,
    onScroll: handleScroll,
    mode,
    onMode: setMode,
    trace,
    pinnedId,
    onPin: pin,
    onFollow: follow,
    pane,
    onPane: setPane,
  };

  return (
    <div className="pi-agent-root" data-agent-surface>
      {mode === "collapsed" ? (
        <button
          type="button"
          className="pi-agent-seal"
          onClick={() => setMode("panel")}
          aria-label="Open the archive agent panel"
          aria-haspopup="dialog"
          aria-expanded={false}
        >
          <span className="pi-agent-seal__rings" aria-hidden="true">
            <TreeMark size={30} />
          </span>
          <span className="pi-agent-seal__copy">
            <span className="pi-agent-seal__label">Ask the archive</span>
            <span className="pi-agent-seal__hint">Agent</span>
          </span>
        </button>
      ) : null}

      {mode === "panel" ? <AgentPanelSurface {...surfaceProps} /> : null}

      {mode === "expanded" ? (
        <div className="pi-agent-overlay">
          <AgentWorkspaceSurface {...surfaceProps} />
        </div>
      ) : null}
    </div>
  );
}
