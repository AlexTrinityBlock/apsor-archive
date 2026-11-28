import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useBlocker,
  useLocation,
  useNavigate,
  useParams,
  type BlockerFunction,
} from "react-router-dom";

import { ApiError } from "../../apis/fetch-client";
import { Button, ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { useToast } from "../component/Toast";
import { useScrollLock } from "../hook/useScrollLock";
import {
  cancelAgentChatAttachment,
  deleteAgentChatAttachment,
  getListAgentChatAttachmentsQueryKey,
  listAgentEntries,
  useCreateAgentConversation,
  useForkAgentConversation,
  useGetAgentConversation,
  useListAgentApprovals,
  useListAgentConversations,
  useUpdateAgentConversation,
} from "../generated-apis-types/agent/agent";
import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import {
  getActiveLocale,
  translate,
  translateApiErrorWithActiveLocale,
  useI18n,
  type TranslationKey,
} from "../i18n";
import {
  buildPersistedWorkTrace,
  mergeWorkTrace,
  type ResourceTarget,
} from "../agent/trace";
import { useMediaQuery } from "../agent/hook/useMediaQuery";
import {
  MAX_CHAT_IMAGES_PER_MESSAGE,
  attachmentView,
  createChatUploadToken,
  isUploadAbortError,
  nameClipboardImage,
  uploadChatAttachment,
  type ComposerAttachment,
} from "./attachments";
import { ApprovalStack } from "./component/ApprovalCard";
import { ChatAttachmentManager } from "./component/ChatAttachmentManager";
import {
  ChatComposer,
  type ChatComposerHandle,
} from "./component/ChatComposer";
import {
  CHAT_PANE_IDS,
  ChatHeader,
  type ChatPane,
} from "./component/ChatHeader";
import { ChatInspector, type InspectorTab } from "./component/ChatInspector";
import { ChatIntro } from "./component/ChatIntro";
import { ChatThread } from "./component/ChatThread";
import { ContextActions } from "./component/ContextActions";
import { ConversationRail } from "./component/ConversationRail";
import { JumpToLatest } from "./component/JumpToLatest";
import { LeaveRunDialog } from "./component/LeaveRunDialog";
import { ResourcePreviewDialog } from "./component/ResourcePreviewDialog";
import { RetryBar } from "./component/RetryBar";
import { StreamingTurn } from "./component/StreamingTurn";
import { StreamErrorBanner, StreamLiveRegion } from "./component/StreamStatus";
import { SPLIT_BASIS_VAR, useChatSplit } from "./hook/useChatSplit";
import {
  useChatStream,
  type ChatStreamView,
  type StreamOutcome,
} from "./hook/useChatStream";
import { useStickToBottom } from "./hook/useStickToBottom";
import {
  readDraft,
  writeDraft,
  type DraftKey,
  type DraftMap,
} from "./draft-map";
import { anchoredScrollTop } from "./scroll-follow";
import { buildMemoryTitles } from "./memory-titles";
import { invalidateConversation, invalidateConversationList } from "./query";
import {
  clearLastChatConversation,
  rememberLastChatConversation,
} from "./session-storage";
import {
  isRecord,
  mergeEntries,
  numberValue,
  readRetryState,
  stringValue,
  type RetryState,
  transcriptText,
  type ChatAttachmentView,
  type CitationToken,
  type ResourceMeta,
} from "./types";
import { titleFromMessage } from "./format";
import "./chat.css";
import "../agent/agent.css";

const PAGE_SIZE = 200;
const NO_ENTRIES: readonly AgentEntrySchema[] = [];
const NARROW_QUERY = "(max-width: 899px)";
const ENTRY_HASH = /^#entry-(\d+)$/;
const ENTRY_HIGHLIGHT_MS = 2_000;

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

interface RouteDraft {
  readonly content: string;
  readonly attachments: readonly ChatAttachmentView[];
}

function readRouteAttachments(value: unknown): ChatAttachmentView[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const attachments: ChatAttachmentView[] = [];
  for (const item of value) {
    if (!isRecord(item)) {
      continue;
    }
    const id = numberValue(item.id);
    const fileName = stringValue(item.fileName);
    const mimeType = stringValue(item.mimeType);
    const sizeBytes = numberValue(item.sizeBytes);
    const width = numberValue(item.width);
    const height = numberValue(item.height);
    const contentUrl = stringValue(item.contentUrl);
    if (
      id === null ||
      fileName === null ||
      mimeType === null ||
      sizeBytes === null ||
      width === null ||
      height === null ||
      contentUrl === null
    ) {
      continue;
    }
    attachments.push({
      id,
      fileName,
      mimeType,
      sizeBytes,
      width,
      height,
      contentUrl,
    });
  }
  return attachments;
}

function readRouteDraft(state: unknown): RouteDraft | null {
  if (!isRecord(state)) {
    return null;
  }
  const content =
    typeof state.draft === "string" ? state.draft.trim() : "";
  const attachments = readRouteAttachments(state.attachments);
  return content.length > 0 || attachments.length > 0
    ? { content, attachments }
    : null;
}

/**
 * A brand-new conversation's first turn is already streaming (or about to
 * start from route state) while the detail request is still in flight.
 */
function isLiveForThread(
  stream: ChatStreamView | null,
  conversationId: number,
  routeState: unknown,
): boolean {
  if (stream !== null && stream.conversationId === conversationId) {
    return true;
  }
  return readRouteDraft(routeState) !== null;
}

/**
 * On narrow screens the inspector is a hidden pane most of the time; mount it
 * only when shown so streaming tokens do not re-render it off screen.
 */
function shouldMountInspector(
  narrow: boolean,
  collapsed: boolean,
  pane: ChatPane,
  hasPreview: boolean,
): boolean {
  if (narrow) {
    return pane === "inspector" || hasPreview;
  }
  return !collapsed;
}

/**
 * The retry bar already shows a stream failure's detail and action, so the
 * banner only remains for failures that cannot be retried.
 */
function visibleBannerError(
  lastError: string | null,
  retryState: RetryState,
): string | null {
  if (retryState.retryable && retryState.reason === "stream_failure") {
    return null;
  }
  return lastError;
}

/** The polite live-region message for the current stream state, if any. */
function liveAnnouncementKey(
  stream: ChatStreamView | null,
  outcome: StreamOutcome | null,
): TranslationKey | null {
  if (stream) {
    return stream.status === "waiting"
      ? "chat.live.waitingApproval"
      : "chat.live.responding";
  }
  return outcome ? `chat.live.${outcome}` : null;
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
  const [previewResource, setPreviewResource] = useState<ResourceMeta | null>(
    null,
  );
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const [highlightedEntryId, setHighlightedEntryId] = useState<number | null>(
    null,
  );
  // One in-memory draft per conversation, so switching threads and coming
  // back keeps what the reader was writing.
  const [drafts, setDrafts] = useState<DraftMap>({});
  const currentDraftKey: DraftKey =
    conversationId === null ? "new" : `${conversationId}`;
  const draft = readDraft(drafts, currentDraftKey);
  const setDraft = useCallback(
    (value: string) => {
      setDrafts((current) => writeDraft(current, currentDraftKey, value));
    },
    [currentDraftKey],
  );
  const composerRef = useRef<ChatComposerHandle>(null);
  const focusComposer = useCallback(() => {
    window.requestAnimationFrame(() => {
      composerRef.current?.focus({ programmatic: true });
    });
  }, []);
  const [composerAttachments, setComposerAttachments] = useState<
    ComposerAttachment[]
  >([]);
  const composerAttachmentsRef = useRef<ComposerAttachment[]>([]);
  const cancelledUploads = useRef<Set<string>>(new Set());
  const uploadControllers = useRef<Map<string, AbortController>>(new Map());
  const [attachmentManagerOpen, setAttachmentManagerOpen] = useState(false);
  const attachmentKey = useRef(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [historyStateId, setHistoryStateId] = useState<number | null>(null);
  const [historyEntries, setHistoryEntries] = useState<AgentEntrySchema[]>([]);
  const [historyCursor, setHistoryCursor] = useState<number | null>(null);
  const [historyHasMore, setHistoryHasMore] = useState<boolean | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const handledRouteDraft = useRef<string | null>(null);
  const handledEntryHash = useRef<string | null>(null);
  const entryHighlightTimer = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollContentRef = useRef<HTMLDivElement>(null);
  const historyInFlightRef = useRef(false);
  const historyRequestIdRef = useRef(0);
  // Scroll metrics captured just before older rows are prepended.
  const olderAnchorRef = useRef<{
    readonly scrollHeight: number;
    readonly scrollTop: number;
  } | null>(null);

  useEffect(() => {
    composerAttachmentsRef.current = composerAttachments;
  }, [composerAttachments]);

  const deleteStagedAttachment = useCallback((attachmentId: number) => {
    // keepalive lets a route change or tab close still reach the delete route.
    void deleteAgentChatAttachment(attachmentId, { keepalive: true }).catch(
      () => {
        // The server-side lifetime sweep removes anything this request misses.
      },
    );
  }, []);

  const cancelStagedUpload = useCallback((clientToken: string) => {
    // A token lets the backend discard an upload whose response never arrived.
    void cancelAgentChatAttachment(
      { client_token: clientToken },
      { keepalive: true },
    ).catch(() => {
      // The staged TTL sweep is the final backstop for a lost abort.
    });
  }, []);

  const clearComposerAttachments = useCallback(() => {
    composerAttachmentsRef.current = [];
    setComposerAttachments([]);
  }, []);

  const discardComposerAttachments = useCallback(() => {
    const current = composerAttachmentsRef.current;
    for (const attachment of current) {
      if (attachment.attachment) {
        deleteStagedAttachment(attachment.attachment.id);
        continue;
      }
      if (attachment.status === "uploading") {
        cancelledUploads.current.add(attachment.key);
      }
      uploadControllers.current.get(attachment.key)?.abort();
      uploadControllers.current.delete(attachment.key);
      cancelStagedUpload(attachment.clientToken);
    }
    composerAttachmentsRef.current = [];
    setComposerAttachments([]);
    if (current.length > 0) {
      void queryClient.invalidateQueries({
        queryKey: getListAgentChatAttachmentsQueryKey(),
      });
    }
  }, [cancelStagedUpload, deleteStagedAttachment, queryClient]);

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
    setPreviewResource(null);
    setInspectorTab("telemetry");
    setLastError(null);
    setPane("thread");
    discardComposerAttachments();
  }, [conversationId, discardComposerAttachments]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(
    () => () => {
      discardComposerAttachments();
    },
    [discardComposerAttachments],
  );

  useEffect(() => {
    const handlePageHide = () => {
      discardComposerAttachments();
    };
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, [discardComposerAttachments]);

  const conversationsQuery = useListAgentConversations({
    status: "active",
    limit: 100,
  });
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

  const addImages = useCallback(
    (files: File[]) => {
      const available = MAX_CHAT_IMAGES_PER_MESSAGE - composerAttachments.length;
      if (available <= 0) {
        toast.info(
          t("chat.attachments.limit", {
            count: formatNumber(MAX_CHAT_IMAGES_PER_MESSAGE),
          }),
        );
        return;
      }
      if (files.length > available) {
        toast.info(
          t("chat.attachments.limit", {
            count: formatNumber(MAX_CHAT_IMAGES_PER_MESSAGE),
          }),
        );
      }
      const accepted = files.slice(0, available).map((file, index) => ({
        file: nameClipboardImage(file, index),
        key: `chat-upload-${Date.now()}-${attachmentKey.current++}`,
        clientToken: createChatUploadToken(),
      }));
      if (accepted.length === 0) {
        return;
      }
      const pending: ComposerAttachment[] = accepted.map((item) => ({
        key: item.key,
        status: "uploading",
        fileName: item.file.name,
        clientToken: item.clientToken,
        progress: 0,
        attachment: null,
        error: null,
      }));
      setComposerAttachments((current) => [...current, ...pending]);
      for (const item of accepted) {
        const controller = new AbortController();
        uploadControllers.current.set(item.key, controller);
        void uploadChatAttachment({
          file: item.file,
          clientToken: item.clientToken,
          signal: controller.signal,
          onProgress: (percent) => {
            setComposerAttachments((current) =>
              current.map((attachment) =>
                attachment.key === item.key
                  ? { ...attachment, progress: percent }
                  : attachment,
              ),
            );
          },
        })
          .then((uploaded) => {
            if (cancelledUploads.current.delete(item.key)) {
              deleteStagedAttachment(uploaded.id);
              void queryClient.invalidateQueries({
                queryKey: getListAgentChatAttachmentsQueryKey(),
              });
              return;
            }
            setComposerAttachments((current) =>
              current.map((attachment) =>
                attachment.key === item.key
                  ? {
                      ...attachment,
                      status: "ready",
                      progress: 100,
                      attachment: attachmentView(uploaded),
                    }
                  : attachment,
              ),
            );
            void queryClient.invalidateQueries({
              queryKey: getListAgentChatAttachmentsQueryKey(),
            });
          })
          .catch((error: unknown) => {
            const cancelled = cancelledUploads.current.delete(item.key);
            if (cancelled || isUploadAbortError(error)) {
              return;
            }
            const detail = describeError(error);
            setComposerAttachments((current) =>
              current.map((attachment) =>
                attachment.key === item.key
                  ? { ...attachment, status: "error", error: detail }
                  : attachment,
              ),
            );
            // A dropped response may still have stored an object server-side.
            cancelStagedUpload(item.clientToken);
            toast.error(detail);
          })
          .finally(() => {
            uploadControllers.current.delete(item.key);
          });
      }
    },
    [
      cancelStagedUpload,
      composerAttachments.length,
      deleteStagedAttachment,
      formatNumber,
      queryClient,
      t,
      toast,
    ],
  );

  const removeImage = useCallback(
    (key: string) => {
      const current = composerAttachmentsRef.current;
      const target = current.find((attachment) => attachment.key === key);
      if (target?.attachment) {
        deleteStagedAttachment(target.attachment.id);
      } else if (target) {
        if (target.status === "uploading") {
          cancelledUploads.current.add(key);
        }
        uploadControllers.current.get(key)?.abort();
        uploadControllers.current.delete(key);
        cancelStagedUpload(target.clientToken);
      }
      const next = current.filter((attachment) => attachment.key !== key);
      composerAttachmentsRef.current = next;
      setComposerAttachments(next);
      if (target) {
        void queryClient.invalidateQueries({
          queryKey: getListAgentChatAttachmentsQueryKey(),
        });
      }
    },
    [cancelStagedUpload, deleteStagedAttachment, queryClient],
  );
  const openAttachmentManager = useCallback(() => {
    setAttachmentManagerOpen(true);
  }, []);
  const closeAttachmentManager = useCallback(() => {
    setAttachmentManagerOpen(false);
  }, []);
  const forgetDeletedAttachment = useCallback((attachmentId: number) => {
    const next = composerAttachmentsRef.current.filter(
      (attachment) => attachment.attachment?.id !== attachmentId,
    );
    composerAttachmentsRef.current = next;
    setComposerAttachments(next);
  }, []);

  const readyAttachments = useMemo(
    () =>
      composerAttachments.flatMap((attachment) =>
        attachment.status === "ready" && attachment.attachment
          ? [attachment.attachment]
          : [],
      ),
    [composerAttachments],
  );
  const attachmentsPending = composerAttachments.some(
    (attachment) => attachment.status !== "ready",
  );

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

  const stickRef = useRef<() => void>(() => undefined);
  const handleStreamError = useCallback((message: string) => {
    stickRef.current();
    setLastError(message);
  }, []);
  const { stream, isStreaming, start, retry, resolveApproval, stop, outcome } =
    useChatStream(handleStreamError);

  // Leaving the page or switching threads disconnects the stream, which the
  // backend records as a stopped run, so a pathname change asks first.
  // Hash-only changes (`#entry-N`) and same-path state rewrites pass.
  const shouldBlock = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation }) =>
      isStreaming && currentLocation.pathname !== nextLocation.pathname,
    [isStreaming],
  );
  const blocker = useBlocker(shouldBlock);
  const stayOnRun = useCallback(() => {
    if (blocker.state === "blocked") {
      blocker.reset();
    }
  }, [blocker]);
  const leaveRun = useCallback(() => {
    if (blocker.state === "blocked") {
      stop();
      blocker.proceed();
    }
  }, [blocker, stop]);

  useEffect(() => {
    if (!isStreaming) {
      return;
    }
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isStreaming]);

  // Abort any open run when the selected thread changes or the page unmounts.
  useEffect(() => {
    stickRef.current();
    return () => stop();
  }, [conversationId, stop]);

  const sendMessage = useCallback(
    (id: number, content: string) => {
      const trimmed = content.trim();
      if ((trimmed.length === 0 && readyAttachments.length === 0) || isStreaming) {
        return;
      }
      stickRef.current();
      setLastError(null);
      setPinnedId(null);
      setDraft("");
      clearComposerAttachments();
      void start(id, trimmed, undefined, readyAttachments);
    },
    [
      clearComposerAttachments,
      isStreaming,
      readyAttachments,
      setDraft,
      start,
    ],
  );

  useEffect(() => {
    if (conversationId === null) {
      return;
    }
    const routeDraft = readRouteDraft(location.state);
    if (!routeDraft) {
      return;
    }
    const key = `${conversationId}:${routeDraft.content}:${routeDraft.attachments
      .map((attachment) => attachment.id)
      .join(",")}`;
    if (handledRouteDraft.current === key) {
      return;
    }
    handledRouteDraft.current = key;
    navigate(location.pathname, { replace: true, state: null });
    setLastError(null);
    setPinnedId(null);
    setDraft("");
    clearComposerAttachments();
    void start(
      conversationId,
      routeDraft.content,
      undefined,
      routeDraft.attachments,
    );
  }, [
    clearComposerAttachments,
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
  const historyForCurrent = historyStateId === conversationId;
  const retainedEntries = historyForCurrent ? historyEntries : NO_ENTRIES;
  const entries = useMemo(
    () => mergeEntries(retainedEntries, baseEntries),
    [baseEntries, retainedEntries],
  );

  // The detail endpoint now returns the newest page. Keep every page the reader
  // has already seen so a later refetch cannot drop the tail that moved out of
  // the page window, and reset the accumulated history on a conversation change.
  /* eslint-disable react-hooks/set-state-in-effect -- paged server rows are accumulated here */
  useEffect(() => {
    historyRequestIdRef.current += 1;
    historyInFlightRef.current = false;
    setHistoryStateId(conversationId);
    setHistoryEntries([]);
    setHistoryCursor(null);
    setHistoryHasMore(null);
    setHistoryLoading(false);
    setHistoryError(null);
  }, [conversationId]);

  useEffect(() => {
    if (
      conversationId === null ||
      conversation?.id !== conversationId ||
      historyStateId !== conversationId
    ) {
      return;
    }
    setHistoryEntries((current) => mergeEntries(current, baseEntries));
  }, [baseEntries, conversation, conversationId, historyStateId]);
  /* eslint-enable react-hooks/set-state-in-effect */
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
      stickRef.current();
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

  const hasOlder =
    historyHasMore === null
      ? (conversation?.entries_has_previous ?? false)
      : historyHasMore;
  const olderCursor =
    historyHasMore === null
      ? (conversation?.entries_previous_before_id ?? null)
      : historyCursor;
  const loadingOlder = historyLoading;
  const olderLoadError = historyForCurrent ? historyError : null;
  const streamToolCount = stream?.toolCalls.length ?? 0;
  const streamTextLength = stream?.assistantText.length ?? 0;
  const streamingActive = stream !== null;

  const followVersion = [
    conversationId,
    entries.length,
    lastError,
    pendingApprovals.length,
    streamingActive,
    streamTextLength,
    streamToolCount,
  ].join("|");
  const follow = useStickToBottom(scrollRef, scrollContentRef, followVersion);
  useEffect(() => {
    stickRef.current = follow.stick;
  }, [follow.stick]);

  // Older pages are prepended; restore the reader's distance from the bottom
  // before paint so the visible message stays put in every browser.
  useLayoutEffect(() => {
    const anchor = olderAnchorRef.current;
    const scroll = scrollRef.current;
    if (!anchor || !scroll) {
      return;
    }
    olderAnchorRef.current = null;
    scroll.scrollTop = anchoredScrollTop(anchor, scroll.scrollHeight);
  }, [entries.length]);

  // A history citation deep-links to one message. The target may arrive with
  // the first conversation page, so `entries` is a dependency; the handled key
  // then prevents later streaming updates from scrolling the reader away.
  // Entries outside the loaded page are not fetched here: the reader can use
  // the existing "load more" control and the hash stays in the URL.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const match = ENTRY_HASH.exec(location.hash);
    const parsedId = match ? Number(match[1]) : NaN;
    const targetId =
      Number.isSafeInteger(parsedId) && parsedId > 0 ? parsedId : null;
    if (targetId === null) {
      handledEntryHash.current = null;
      setHighlightedEntryId(null);
      return;
    }
    const key = `${conversationId ?? 0}:${location.hash}`;
    if (handledEntryHash.current === key) {
      return;
    }
    // Wait until the entry is actually in the rendered page before scrolling.
    if (!entries.some((entry) => entry.id === targetId)) {
      return;
    }
    const target = document.getElementById(`entry-${targetId}`);
    if (!target) {
      return;
    }
    handledEntryHash.current = key;
    follow.unstick();
    target.scrollIntoView({ block: "center" });
    setHighlightedEntryId(targetId);
    if (entryHighlightTimer.current !== null) {
      window.clearTimeout(entryHighlightTimer.current);
    }
    entryHighlightTimer.current = window.setTimeout(() => {
      setHighlightedEntryId(null);
      entryHighlightTimer.current = null;
    }, ENTRY_HIGHLIGHT_MS);
  }, [conversationId, entries, follow, location.hash]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(
    () => () => {
      if (entryHighlightTimer.current !== null) {
        window.clearTimeout(entryHighlightTimer.current);
        entryHighlightTimer.current = null;
      }
    },
    [],
  );

  const submit = async (value: string) => {
    const trimmed = value.trim();
    if (attachmentsPending) {
      return;
    }
    if (trimmed.length === 0 && readyAttachments.length === 0) {
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
              t("chat.attachments.imageConversationTitle"),
          },
        });
        await invalidateConversationList(queryClient);
        setDraft("");
        clearComposerAttachments();
        navigate(`/chat/${created.id}`, {
          replace: true,
          state: { draft: trimmed, attachments: readyAttachments },
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
    follow.stick();
    setLastError(null);
    setPinnedId(null);
    void retry(conversationId, retryState.lastUserText);
  }, [
    conversationId,
    follow,
    retry,
    retryState.lastUserText,
    retryState.retryable,
  ]);

  const loadOlder = async () => {
    if (
      conversationId === null ||
      olderCursor === null ||
      historyInFlightRef.current
    ) {
      return;
    }
    const requestId = historyRequestIdRef.current + 1;
    historyRequestIdRef.current = requestId;
    historyInFlightRef.current = true;
    follow.unstick();
    setHistoryStateId(conversationId);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const page = await listAgentEntries(conversationId, {
        before_id: olderCursor,
        limit: PAGE_SIZE,
      });
      if (historyRequestIdRef.current !== requestId) {
        return;
      }
      const scroll = scrollRef.current;
      olderAnchorRef.current = scroll
        ? { scrollHeight: scroll.scrollHeight, scrollTop: scroll.scrollTop }
        : null;
      setHistoryEntries((current) =>
        mergeEntries(historyForCurrent ? current : baseEntries, page.entries),
      );
      setHistoryCursor(page.previous_before_id ?? null);
      setHistoryHasMore(page.has_previous ?? false);
    } catch (error) {
      if (historyRequestIdRef.current !== requestId) {
        return;
      }
      setHistoryError(describeError(error));
    } finally {
      if (historyRequestIdRef.current === requestId) {
        historyInFlightRef.current = false;
        setHistoryLoading(false);
      }
    }
  };

  const startNewConversation = useCallback(() => {
    clearLastChatConversation();
    discardComposerAttachments();
    setDraft("");
    setLastError(null);
    setPinnedId(null);
    setPreviewTarget(null);
    setPreviewResource(null);
    setInspectorTab("telemetry");
    setPane("thread");
    if (narrow) {
      setDrawerOpen(false);
    }
    navigate("/chat");
    focusComposer();
  }, [
    discardComposerAttachments,
    focusComposer,
    navigate,
    narrow,
    setDraft,
    setDrawerOpen,
  ]);

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

  const openMemoryPreview = useCallback(
    (memoryId: number, title: string | null) => {
      setPreviewTarget({ type: "memory", id: memoryId, chunk: null, title });
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
        openMemoryPreview(token.id, memoryTitles.get(token.id) ?? null);
      }
    },
    [memoryTitles, openFilePreview, openMemoryPreview],
  );

  const handleOpenResource = useCallback((resource: ResourceMeta) => {
    if (resource.resourceId === null) {
      return;
    }
    setPreviewResource(resource);
  }, []);

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

  const collapseInspector = useCallback(() => {
    setCollapsed(true);
  }, [setCollapsed]);

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

  // Pending approvals and the live turn trail the persisted transcript.
  const liveTail = (
    <>
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
    </>
  );

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
          onSuggestion={(text) => {
            setDraft(text);
            focusComposer();
          }}
          disabled={creating}
        />
      );
    }
    if (conversationQuery.isLoading) {
      // Render the live first turn instead of flashing the loading card.
      if (isLiveForThread(stream, conversationId, location.state)) {
        return liveTail;
      }
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
        {hasOlder ? (
          <div className="chat-thread__more chat-thread__more--older">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void loadOlder()}
              disabled={loadingOlder}
            >
              {loadingOlder ? (
                <>
                  <Loader size={14} label={t("chat.page.loadingMoreLabel")} />
                  {t("chat.page.loadingMore")}
                </>
              ) : (
                <>
                  <Icon name="arrow-up" size={14} />
                  {t("chat.page.loadMore")}
                </>
              )}
            </Button>
          </div>
        ) : null}
        {olderLoadError ? (
          <p className="chat-thread__more-error" role="alert">
            {t("chat.page.moreError")}{" "}
            <button type="button" onClick={() => void loadOlder()}>
              {t("chat.page.moreErrorRetry")}
            </button>
          </p>
        ) : null}
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
          highlightedEntryId={highlightedEntryId}
        />
        {liveTail}
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
          composerRef={composerRef}
          value={draft}
          onChange={setDraft}
          onSubmit={(value) => void submit(value)}
          attachments={composerAttachments}
          onAddImages={addImages}
          onRemoveAttachment={removeImage}
          onManageAttachments={openAttachmentManager}
          pending={creating || isStreaming}
          streaming={isStreaming}
          disabled={
            creating ||
            waitingForApproval ||
            (conversationId !== null && conversationQuery.isError)
          }
          blockReason={waitingForApproval ? "approval" : null}
          onStop={stop}
        />
      </>
    );
  };

  const bannerError = visibleBannerError(lastError, retryState);
  const liveMessage = liveAnnouncementKey(stream, outcome);

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
      id={CHAT_PANE_IDS.thread}
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
        tabIndex={-1}
      >
        <div className="chat-stream__inner" ref={scrollContentRef}>
          {threadContent()}
          <StreamErrorBanner
            detail={bannerError}
            onDismiss={() => setLastError(null)}
          />
        </div>
      </div>

      <div className="chat-composer-dock">
        <JumpToLatest
          visible={!follow.stuck && conversationId !== null}
          hasNewActivity={follow.hasNewActivity}
          onJump={follow.scrollToLatest}
        />
        {composer()}
      </div>
      <StreamLiveRegion message={liveMessage} />
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
      onCollapse={collapseInspector}
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

          {shouldMountInspector(
            narrow,
            collapsed,
            pane,
            previewTarget !== null,
          ) ? (
            <div
              id="chat-inspector"
              className="chat-inspector-slot"
              style={{
                flexBasis: `var(${SPLIT_BASIS_VAR}, ${ratio * 100}%)`,
              }}
            >
              {inspector}
            </div>
          ) : null}
        </div>
      </div>
      <ChatAttachmentManager
        open={attachmentManagerOpen}
        onClose={closeAttachmentManager}
        onDeleted={forgetDeletedAttachment}
      />
      <ResourcePreviewDialog
        resource={previewResource}
        onClose={() => setPreviewResource(null)}
      />
      <LeaveRunDialog
        open={blocker.state === "blocked"}
        onStay={stayOnRun}
        onLeave={leaveRun}
      />
    </div>
  );
}
