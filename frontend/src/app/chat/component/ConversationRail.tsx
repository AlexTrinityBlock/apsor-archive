import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../../apis/fetch-client";
import { Button } from "../../component/Button";
import { ContextMenu, type ContextMenuItem } from "../../component/ContextMenu";
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
import { visibleConversations } from "./rail-conversations";

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

interface SessionMenuState {
  readonly id: number;
  readonly x: number;
  readonly y: number;
  readonly anchor: HTMLElement;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Return focus to a session row's link after an inline edit closes. */
function focusSessionAnchor(conversationId: number): void {
  window.requestAnimationFrame(() => {
    document
      .querySelector<HTMLElement>(`[data-session-anchor="${conversationId}"]`)
      ?.focus();
  });
}

/** Return focus to the header's drawer toggle when the overlay closes. */
function focusDrawerToggle(): void {
  window.requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(".chat-header__drawer")?.focus();
  });
}

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

/** Session drawer: grouped conversations with rename, delete, and fork. */
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

  const [menu, setMenu] = useState<SessionMenuState | null>(null);
  const menuId = menu?.id ?? null;
  const asideRef = useRef<HTMLElement>(null);
  const collapseRef = useRef<HTMLButtonElement>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [forkingId, setForkingId] = useState<number | null>(null);
  const [removedIds, setRemovedIds] = useState<ReadonlySet<number>>(
    () => new Set(),
  );

  // The overlay drawer is a modal: focus enters it, Tab stays inside, and
  // focus returns to the header toggle when it closes.
  const wasOverlayOpen = useRef(false);
  useEffect(() => {
    const overlayOpen = open && overlay;
    if (overlayOpen) {
      const frame = window.requestAnimationFrame(() => {
        collapseRef.current?.focus();
      });
      wasOverlayOpen.current = true;
      return () => window.cancelAnimationFrame(frame);
    }
    if (wasOverlayOpen.current) {
      wasOverlayOpen.current = false;
      focusDrawerToggle();
    }
    return undefined;
  }, [open, overlay]);

  const trapFocus = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (!overlay || event.key !== "Tab") {
      return;
    }
    const aside = asideRef.current;
    if (!aside) {
      return;
    }
    const focusable = Array.from(
      aside.querySelectorAll<HTMLElement>(FOCUSABLE),
    ).filter((element) => element.offsetParent !== null);
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const visible = useMemo(
    () => visibleConversations(conversations, removedIds),
    [conversations, removedIds],
  );

  const grouped = useMemo(() => {
    const buckets = new Map<SessionGroup, AgentConversationSchema[]>();
    for (const { key } of GROUP_ORDER) {
      buckets.set(key, []);
    }
    for (const conversation of visible) {
      buckets.get(groupOf(conversation))?.push(conversation);
    }
    for (const bucket of buckets.values()) {
      bucket.sort((left, right) => timestampOf(right) - timestampOf(left));
    }
    return GROUP_ORDER.map((group) => ({
      ...group,
      items: buckets.get(group.key) ?? [],
    }));
  }, [visible]);

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
      focusSessionAnchor(conversation.id);
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
      focusSessionAnchor(conversation.id);
      toast.success(t("chat.rail.renamed"));
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  const deleteConversation = async (conversation: AgentConversationSchema) => {
    if (busyId !== null || forkingId !== null) {
      return;
    }
    setBusyId(conversation.id);
    setRemovedIds((current) => new Set(current).add(conversation.id));
    try {
      // The API has no hard delete: `archived` is the soft-delete tag that
      // keeps the row and its entries while hiding the conversation from the
      // active list.
      await updateConversation.mutateAsync({
        conversationId: conversation.id,
        data: { status: "archived" },
      });
      await refresh(conversation.id);
      toast.success(t("chat.rail.archivedUndoToast"), {
        action: {
          label: t("chat.rail.undo"),
          onAction: () => void restoreConversation(conversation),
        },
      });
      if (activeId === conversation.id) {
        clearLastChatConversation();
        navigate("/chat");
        onNavigate();
      }
    } catch (caught) {
      setRemovedIds((current) => {
        if (!current.has(conversation.id)) {
          return current;
        }
        const next = new Set(current);
        next.delete(conversation.id);
        return next;
      });
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  // "Delete" is a soft archive, so Undo simply makes the thread active again.
  const restoreConversation = async (conversation: AgentConversationSchema) => {
    try {
      await updateConversation.mutateAsync({
        conversationId: conversation.id,
        data: { status: "active" },
      });
      setRemovedIds((current) => {
        if (!current.has(conversation.id)) {
          return current;
        }
        const next = new Set(current);
        next.delete(conversation.id);
        return next;
      });
      await refresh(conversation.id);
      toast.success(t("chat.rail.restoredToast"));
    } catch (caught) {
      toast.error(describeError(caught));
    }
  };

  const openSessionMenu = (
    event: ReactMouseEvent<HTMLButtonElement>,
    conversation: AgentConversationSchema,
  ) => {
    if (menuId === conversation.id) {
      setMenu(null);
      return;
    }
    const anchor = event.currentTarget;
    const rect = anchor.getBoundingClientRect();
    setMenu({ id: conversation.id, x: rect.left, y: rect.bottom + 4, anchor });
  };

  const menuConversation =
    menu === null
      ? null
      : (visible.find((conversation) => conversation.id === menu.id) ?? null);
  const menuItems: readonly ContextMenuItem[] =
    menuConversation === null
      ? []
      : [
          {
            id: "rename",
            label: t("chat.rail.rename"),
            icon: "pencil",
            onSelect: () => {
              setEditingId(menuConversation.id);
              setEditTitle(menuConversation.title);
            },
          },
          {
            id: "delete",
            label: t("chat.rail.delete"),
            icon: "trash",
            danger: true,
            onSelect: () => void deleteConversation(menuConversation),
          },
          {
            id: "fork",
            label: t("chat.rail.fork"),
            icon: "branch",
            disabled: forkingId !== null,
            onSelect: () => void forkThread(menuConversation),
          },
        ];

  const forkThread = async (conversation: AgentConversationSchema) => {
    if (busyId !== null || forkingId !== null) {
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
  } else if (visible.length === 0) {
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
                        busy ? "is-busy" : null,
                        menuOpen ? "is-menu-open" : null,
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
                                focusSessionAnchor(conversation.id);
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
                              onClick={() => {
                                setEditingId(null);
                                focusSessionAnchor(conversation.id);
                              }}
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
                            data-session-anchor={conversation.id}
                            onClick={() => {
                              setMenu(null);
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
                              </span>
                            </span>
                          </Link>

                          {active ? (
                            <span
                              className="chat-session__dot"
                              aria-label={t("chat.rail.current")}
                            />
                          ) : null}

                          <div className="chat-session__menu">
                            <button
                              type="button"
                              className="chat-session__menu-btn"
                              onClick={(event) =>
                                openSessionMenu(event, conversation)
                              }
                              aria-label={t("chat.rail.actionsFor", {
                                title: conversation.title,
                              })}
                              aria-haspopup="menu"
                              aria-expanded={menuOpen}
                              disabled={busy || forking}
                            >
                              {forking ? (
                                <Loader
                                  size={12}
                                  label={t("chat.rail.forkingLabel")}
                                />
                              ) : (
                                <span aria-hidden="true">⋯</span>
                              )}
                            </button>
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

  const asideClassName = [
    "chat-sessions",
    overlay ? "chat-sessions--overlay" : null,
    open ? "is-open" : "is-collapsed",
  ]
    .filter(Boolean)
    .join(" ");
  const modal = open && overlay;

  return (
    <>
      {modal ? (
        <button
          type="button"
          className="chat-scrim"
          onClick={onClose}
          aria-label={t("chat.rail.close")}
          tabIndex={-1}
        />
      ) : null}
      <aside
        ref={asideRef}
        id="chat-sessions"
        className={asideClassName}
        aria-label={t("chat.rail.aria")}
        aria-hidden={open ? undefined : true}
        inert={!open}
        role={modal ? "dialog" : undefined}
        aria-modal={modal ? true : undefined}
        onKeyDown={trapFocus}
      >
        {/*
          The header bar owns the rail toggle and New chat. Only the phone
          drawer keeps a compact head, because it covers the header and needs
          its own close and New chat controls.
        */}
        {overlay ? (
          <div className="chat-sessions__head">
            <span className="mono-label">{t("chat.rail.heading")}</span>
            <button
              type="button"
              className="chat-sessions__new-icon"
              onClick={() => {
                clearLastChatConversation();
                onNew();
              }}
              aria-label={t("chat.rail.newChat")}
              title={t("chat.rail.newChat")}
            >
              <Icon name="plus" size={13} />
            </button>
            <button
              type="button"
              ref={collapseRef}
              className="chat-sessions__collapse"
              onClick={onClose}
              aria-label={t("chat.rail.collapse")}
              title={t("chat.rail.collapse")}
            >
              <Icon name="panel-left-close" size={13} />
            </button>
          </div>
        ) : null}

        {body}

        <div className="chat-sessions__foot">
          <span>
            {t("chat.rail.conversationCount", {
              count: formatNumber(visible.length),
            })}
          </span>
        </div>
      </aside>
      {menu && menuConversation ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems}
          label={t("chat.rail.actionsFor", { title: menuConversation.title })}
          onClose={() => setMenu(null)}
          returnFocus={menu.anchor}
        />
      ) : null}
    </>
  );
});
