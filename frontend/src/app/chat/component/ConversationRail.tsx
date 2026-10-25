import { memo, useEffect, useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../../apis/fetch-client";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useForkAgentConversation,
  useUpdateAgentConversation,
} from "../../generated-apis-types/agent/agent";
import type { AgentConversationSchema } from "../../generated-apis-types/schemas";
import { useI18n, getActiveLocale, translate, translateApiErrorWithActiveLocale } from "../../i18n";
import {
  invalidateConversation,
  invalidateConversationList,
} from "../query";
import { clearLastChatConversation } from "../session-storage";

interface ConversationRailProps {
  readonly conversations: readonly AgentConversationSchema[];
  readonly loading: boolean;
  readonly error: unknown;
  readonly activeId: number | null;
  readonly open: boolean;
  readonly overlay: boolean;
  readonly onRetry: () => void;
  readonly onNew: () => void;
  readonly onClose: () => void;
  readonly onNavigate: () => void;
}

type SessionGroup = "today" | "week" | "earlier";

const GROUP_ORDER: ReadonlyArray<{
  key: SessionGroup;
  labelKey:
    | "chat.rail.today"
    | "chat.rail.week"
    | "chat.rail.earlier";
}> = [
  { key: "today", labelKey: "chat.rail.today" },
  { key: "week", labelKey: "chat.rail.week" },
  { key: "earlier", labelKey: "chat.rail.earlier" },
];

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return translateApiErrorWithActiveLocale(error, "chat.rail.listError");
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return translate(getActiveLocale(), "chat.rail.listError");
}

function timestampOf(conversation: AgentConversationSchema): number {
  const raw = conversation.last_entry_at ?? conversation.created_at;
  const time = Date.parse(raw);
  return Number.isNaN(time) ? 0 : time;
}

function groupOf(conversation: AgentConversationSchema): SessionGroup {
  const time = timestampOf(conversation);
  if (time === 0) {
    return "earlier";
  }
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  if (time >= startOfToday) {
    return "today";
  }
  if (time >= startOfToday - 7 * 24 * 60 * 60 * 1000) {
    return "week";
  }
  return "earlier";
}

/** Session drawer: grouped conversations with rename, archive, and fork. */
export const ConversationRail = memo(function ConversationRail({
  conversations,
  loading,
  error,
  activeId,
  open,
  overlay,
  onRetry,
  onNew,
  onClose,
  onNavigate,
}: ConversationRailProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { t, formatNumber, formatRelative } = useI18n();
  const updateConversation = useUpdateAgentConversation();
  const forkConversation = useForkAgentConversation();

  const [menuId, setMenuId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [forkingId, setForkingId] = useState<number | null>(null);

  useEffect(() => {
    if (menuId === null) {
      return;
    }
    const handlePointer = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(`[data-session-menu="${menuId}"]`) !== null
      ) {
        return;
      }
      setMenuId(null);
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuId(null);
      }
    };
    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuId]);

  const grouped = useMemo(() => {
    const buckets = new Map<SessionGroup, AgentConversationSchema[]>();
    for (const { key } of GROUP_ORDER) {
      buckets.set(key, []);
    }
    for (const conversation of conversations) {
      buckets.get(groupOf(conversation))?.push(conversation);
    }
    for (const bucket of buckets.values()) {
      bucket.sort((left, right) => timestampOf(right) - timestampOf(left));
    }
    return GROUP_ORDER.map((group) => ({
      ...group,
      items: buckets.get(group.key) ?? [],
    }));
  }, [conversations]);

  const activeCount = conversations.filter(
    (conversation) => conversation.status === "active",
  ).length;
  const archivedCount = conversations.length - activeCount;

  const refresh = async (conversationId?: number) => {
    await Promise.all([
      invalidateConversationList(queryClient),
      conversationId === undefined
        ? Promise.resolve()
        : invalidateConversation(queryClient, conversationId),
    ]);
  };

  const saveTitle = async (conversation: AgentConversationSchema) => {
    if (busyId !== null || forkingId !== null) {
      return;
    }
    const nextTitle = editTitle.trim();
    if (nextTitle.length === 0 || nextTitle === conversation.title) {
      setEditingId(null);
      return;
    }
    setBusyId(conversation.id);
    try {
      await updateConversation.mutateAsync({
        conversationId: conversation.id,
        data: { title: nextTitle },
      });
      await refresh(conversation.id);
      setEditingId(null);
      toast.success(t("chat.rail.renamed"));
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  const toggleStatus = async (conversation: AgentConversationSchema) => {
    if (busyId !== null || forkingId !== null) {
      return;
    }
    const nextStatus =
      conversation.status === "archived" ? "active" : "archived";
    setBusyId(conversation.id);
    try {
      await updateConversation.mutateAsync({
        conversationId: conversation.id,
        data: { status: nextStatus },
      });
      await refresh(conversation.id);
      toast.success(
        nextStatus === "archived"
          ? t("chat.rail.archivedToast")
          : t("chat.rail.restoredToast"),
      );
      if (nextStatus === "archived" && activeId === conversation.id) {
        clearLastChatConversation();
        navigate("/chat");
        onNavigate();
      }
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  const forkThread = async (conversation: AgentConversationSchema) => {
    if (
      busyId !== null ||
      forkingId !== null ||
      conversation.status !== "active"
    ) {
      return;
    }
    setForkingId(conversation.id);
    try {
      const forked = await forkConversation.mutateAsync({
        conversationId: conversation.id,
        data: {},
      });
      await invalidateConversationList(queryClient);
      toast.success(t("chat.rail.forkToast", { title: conversation.title }));
      navigate(`/chat/${forked.id}`);
      onNavigate();
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setForkingId(null);
    }
  };

  const handleTitleSubmit = (
    event: FormEvent<HTMLFormElement>,
    conversation: AgentConversationSchema,
  ) => {
    event.preventDefault();
    void saveTitle(conversation);
  };

  let body;
  if (loading) {
    body = (
      <div className="chat-sessions__state" role="status" aria-live="polite">
        <Loader size={22} label={t("chat.rail.loadingLabel")} />
        <span>{t("chat.rail.loading")}</span>
      </div>
    );
  } else if (error) {
    body = (
      <div className="chat-sessions__state chat-sessions__state--error" role="alert">
        <p>{describeError(error)}</p>
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {t("chat.rail.retry")}
        </Button>
      </div>
    );
  } else if (conversations.length === 0) {
    body = (
      <div className="chat-sessions__state">
        <p className="mono-label">{t("chat.rail.emptyLabel")}</p>
        <p>{t("chat.rail.emptyDetail")}</p>
      </div>
    );
  } else {
    body = (
      <div className="chat-sessions__scroll">
        {grouped.map((group) =>
          group.items.length === 0 ? null : (
            <section className="chat-sessions__group" key={group.key}>
              <p className="chat-sessions__group-label">
                {t(group.labelKey)}
              </p>
              <ul className="chat-sessions__list">
                {group.items.map((conversation) => {
                  const active = conversation.id === activeId;
                  const archived = conversation.status === "archived";
                  const busy = busyId === conversation.id;
                  const forking = forkingId === conversation.id;
                  const editing = editingId === conversation.id;
                  const menuOpen = menuId === conversation.id;
                  const timestamp =
                    conversation.last_entry_at ?? conversation.created_at;
                  return (
                    <li
                      className={[
                        "chat-session",
                        active ? "is-active" : null,
                        archived ? "is-archived" : null,
                        busy ? "is-busy" : null,
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      key={conversation.id}
                    >
                      {editing ? (
                        <form
                          className="chat-session__edit"
                          onSubmit={(event) =>
                            handleTitleSubmit(event, conversation)
                          }
                        >
                          <label
                            className="visually-hidden"
                            htmlFor={`chat-session-title-${conversation.id}`}
                          >
                            {t("chat.rail.titleLabel")}
                          </label>
                          <input
                            id={`chat-session-title-${conversation.id}`}
                            className="input"
                            value={editTitle}
                            onChange={(event) => setEditTitle(event.target.value)}
                            maxLength={200}
                            autoFocus
                            onKeyDown={(event) => {
                              if (event.key === "Escape") {
                                event.preventDefault();
                                event.stopPropagation();
                                setEditingId(null);
                              }
                            }}
                          />
                          <div className="chat-session__edit-actions">
                            <Button
                              type="submit"
                              size="sm"
                              variant="ink"
                              disabled={busy}
                            >
                              {t("chat.rail.save")}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditingId(null)}
                            >
                              {t("chat.rail.cancel")}
                            </Button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <Link
                            className="chat-session__anchor"
                            to={`/chat/${conversation.id}`}
                            onClick={() => {
                              setMenuId(null);
                              onNavigate();
                            }}
                            aria-current={active ? "page" : undefined}
                          >
                            <span className="chat-session__icon" aria-hidden="true">
                              <Icon name="chat" size={13} />
                            </span>
                            <span className="chat-session__copy">
                              <span className="chat-session__title">
                                {conversation.title}
                              </span>
                              <span className="chat-session__meta">
                                <span>{conversation.model}</span>
                                <span aria-hidden="true">·</span>
                                <time dateTime={timestamp}>
                                  {formatRelative(timestamp)}
                                </time>
                                {archived ? (
                                  <>
                                    <span aria-hidden="true">·</span>
                                    <span className="chat-session__flag">
                                      {t("chat.rail.archivedFlag")}
                                    </span>
                                  </>
                                ) : null}
                              </span>
                            </span>
                          </Link>

                          {active ? (
                            <span
                              className="chat-session__dot"
                              aria-label={t("chat.rail.current")}
                            />
                          ) : null}

                          <div
                            className="chat-session__menu"
                            data-session-menu={conversation.id}
                          >
                            <button
                              type="button"
                              className="chat-session__menu-btn"
                              onClick={() =>
                                setMenuId(menuOpen ? null : conversation.id)
                              }
                              aria-label={t("chat.rail.actionsFor", {
                                title: conversation.title,
                              })}
                              aria-expanded={menuOpen}
                              disabled={busy || forking}
                            >
                              <span aria-hidden="true">⋯</span>
                            </button>
                            {menuOpen ? (
                              <div
                                className="chat-session__menu-panel"
                                role="group"
                                aria-label={t("chat.rail.actionsFor", {
                                  title: conversation.title,
                                })}
                              >
                                <button
                                  type="button"
                                  onClick={() => {
                                    setMenuId(null);
                                    setEditingId(conversation.id);
                                    setEditTitle(conversation.title);
                                  }}
                                >
                                  <Icon name="pencil" size={13} />
                                  {t("chat.rail.rename")}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setMenuId(null);
                                    void toggleStatus(conversation);
                                  }}
                                >
                                  <Icon
                                    name={archived ? "history" : "archive"}
                                    size={13}
                                  />
                                  {archived
                                    ? t("chat.rail.restore")
                                    : t("chat.rail.archive")}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setMenuId(null);
                                    void forkThread(conversation);
                                  }}
                                  disabled={archived}
                                  title={
                                    archived
                                      ? t("chat.rail.forkDisabled")
                                      : t("chat.rail.forkTitle")
                                  }
                                >
                                  {forking ? (
                                    <Loader
                                      size={12}
                                      label={t("chat.rail.forkingLabel")}
                                    />
                                  ) : (
                                    <Icon name="branch" size={13} />
                                  )}
                                  {t("chat.rail.fork")}
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ),
        )}
      </div>
    );
  }

  if (!open) {
    return (
      <aside
        id="chat-sessions"
        className="chat-sessions is-collapsed"
        aria-hidden="true"
      />
    );
  }

  return (
    <>
      {overlay ? (
        <button
          type="button"
          className="chat-scrim"
          onClick={onClose}
          aria-label={t("chat.rail.close")}
        />
      ) : null}
      <aside
        id="chat-sessions"
        className={
          overlay
            ? "chat-sessions chat-sessions--overlay is-open"
            : "chat-sessions is-open"
        }
        aria-label={t("chat.rail.aria")}
      >
        <div className="chat-sessions__head">
          <div className="chat-sessions__head-row">
            <span className="mono-label">{t("chat.rail.heading")}</span>
            <button
              type="button"
              className="chat-sessions__collapse"
              onClick={onClose}
              aria-label={t("chat.rail.collapse")}
              title={t("chat.rail.collapse")}
            >
              <Icon name="chevron-right" size={13} />
            </button>
          </div>
          <Button
            variant="ink"
            size="sm"
            block
            className="chat-sessions__new"
            onClick={() => {
              clearLastChatConversation();
              onNew();
            }}
          >
            <Icon name="plus" size={13} />
            {t("chat.rail.newChat")}
          </Button>
        </div>

        {body}

        <div className="chat-sessions__foot">
          <span>
            {t("chat.rail.counts", {
              active: formatNumber(activeCount),
              archived: formatNumber(archivedCount),
            })}
          </span>
        </div>
      </aside>
    </>
  );
});
