import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import type { AgentConversationDetailSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { clearLastChatConversation } from "../session-storage";

export type ChatPane = "thread" | "inspector";

/** Element ids of the thread and the inspector the header controls. */
export const CHAT_PANE_IDS: Readonly<Record<ChatPane, string>> = {
  thread: "chat-thread-pane",
  inspector: "chat-inspector",
};

/** The header's inspector toggle; focus returns here when the drawer closes. */
export const INSPECTOR_TOGGLE_ID = "chat-inspector-toggle";

export interface ChatHeaderStatus {
  readonly streaming: boolean;
  readonly entries: number;
  readonly awaitingApprovals: number;
}

interface ChatHeaderProps {
  readonly conversation: AgentConversationDetailSchema | null;
  readonly conversationId: number | null;
  readonly transcript: string;
  readonly archived: boolean;
  readonly drawerOpen: boolean;
  readonly status: ChatHeaderStatus;
  readonly inspectorOpen: boolean;
  readonly onToggleDrawer: () => void;
  readonly onToggleInspector: () => void;
  readonly onNew: () => void;
  /** Saves a new title; rejects when the save fails so the edit stays open. */
  readonly onRename: (title: string) => Promise<void>;
  readonly contextActions: ReactNode;
}

/**
 * The single chat bar: conversations toggle, the conversation title (click to
 * rename), a compact status, the inspector toggle, New chat, copy, and the
 * overflow menu. It replaces the old page header + session bar stack so the
 * transcript keeps the vertical space.
 */
export function ChatHeader({
  conversation,
  conversationId,
  transcript,
  archived,
  drawerOpen,
  status,
  inspectorOpen,
  onToggleDrawer,
  onToggleInspector,
  onNew,
  onRename,
  contextActions,
}: ChatHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const { t, formatNumber, formatRelative } = useI18n();

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const handlePointer = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        menuRef.current !== null &&
        menuRef.current.contains(target)
      ) {
        return;
      }
      setMenuOpen(false);
    };
    const handleKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        // Close only this layer; the page's drawer Escape must not also fire.
        event.stopPropagation();
        setMenuOpen(false);
        triggerRef.current?.focus();
      }
    };
    const frame = window.requestAnimationFrame(() => {
      panelRef.current
        ?.querySelector<HTMLElement>(
          'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )
        ?.focus();
    });
    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuOpen]);

  const title =
    conversation?.title ??
    (conversationId === null
      ? t("chat.header.newConversation")
      : t("chat.header.conversation", { id: conversationId }));
  const updated = conversation
    ? conversation.last_entry_at ?? conversation.created_at
    : null;
  const details = conversation
    ? [
        conversation.provider,
        conversation.model,
        updated
          ? t("chat.common.updatedAt", { time: formatRelative(updated) })
          : null,
      ]
        .filter((item): item is string => Boolean(item))
        .join(" · ")
    : t("chat.header.placeholder");
  const parentId = conversation?.parent_conversation_id ?? null;

  let statusText: string | null = null;
  let statusTone: "live" | "wait" | "quiet" = "quiet";
  if (status.streaming) {
    statusText = t("chat.header.statusResponding");
    statusTone = "live";
  } else if (status.awaitingApprovals > 0) {
    statusText = t("chat.page.awaitingApproval", {
      count: formatNumber(status.awaitingApprovals),
    });
    statusTone = "wait";
  } else if (conversationId !== null) {
    statusText = t(
      status.entries === 1 ? "chat.common.entryOne" : "chat.common.entryOther",
      { count: formatNumber(status.entries) },
    );
  }

  return (
    <header className="chat-header">
      <button
        type="button"
        className="chat-icon-btn chat-header__drawer"
        onClick={onToggleDrawer}
        aria-expanded={drawerOpen}
        aria-controls="chat-sessions"
        aria-label={
          drawerOpen
            ? t("chat.header.hideConversations")
            : t("chat.header.showConversations")
        }
        title={
          drawerOpen
            ? t("chat.header.hideConversations")
            : t("chat.header.showConversations")
        }
      >
        <Icon
          name={drawerOpen ? "panel-left-close" : "panel-left-open"}
          size={14}
        />
      </button>

      <div className="chat-header__titles" title={details}>
        <h1 className="chat-header__title">
          <ConversationTitle
            key={`${conversationId ?? "new"}:${title}`}
            title={title}
            editable={conversationId !== null && !archived}
            onRename={onRename}
          />
        </h1>
        {statusText ? (
          <span
            className={`chat-header__status chat-header__status--${statusTone}`}
          >
            {statusTone === "live" ? (
              <span className="chat-pulse" aria-hidden="true" />
            ) : null}
            {statusText}
          </span>
        ) : null}
        {archived ? <Badge tone="ochre">{t("chat.header.archived")}</Badge> : null}
        {parentId !== null ? (
          <Link
            className="chat-header__fork"
            to={`/chat/${parentId}`}
            title={t("chat.header.openParent")}
          >
            <Badge tone="neutral">{t("chat.header.forkOf", { id: parentId })}</Badge>
          </Link>
        ) : null}
      </div>

      <div className="chat-header__actions">
        <button
          type="button"
          id={INSPECTOR_TOGGLE_ID}
          className={[
            "chat-icon-btn",
            "chat-header__inspector",
            inspectorOpen ? "is-active" : null,
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={() => {
            setMenuOpen(false);
            onToggleInspector();
          }}
          aria-expanded={inspectorOpen}
          aria-controls={CHAT_PANE_IDS.inspector}
          aria-label={
            inspectorOpen
              ? t("chat.header.hideInspector")
              : t("chat.header.showInspector")
          }
          title={
            inspectorOpen
              ? t("chat.header.hideInspector")
              : t("chat.header.showInspector")
          }
        >
          <Icon name="layers" size={14} />
        </button>

        <Button
          variant="ink"
          size="sm"
          aria-label={t("chat.header.newChat")}
          onClick={() => {
            setMenuOpen(false);
            clearLastChatConversation();
            onNew();
          }}
        >
          <Icon name="plus" size={13} />
          <span>{t("chat.header.newChat")}</span>
        </Button>

        <CopyButton
          value={transcript}
          label={t("chat.header.copyConversation")}
          iconOnly
          disabled={transcript.length === 0}
          className="chat-header__copy-icon"
        />

        <div className="chat-header__menu" ref={menuRef}>
          <button
            ref={triggerRef}
            type="button"
            className="chat-icon-btn"
            onClick={() => setMenuOpen((value) => !value)}
            aria-label={t("chat.header.threadActions")}
            aria-controls={menuOpen ? panelId : undefined}
            aria-expanded={menuOpen}
            title={t("chat.header.threadActions")}
          >
            <span aria-hidden="true">⋯</span>
          </button>
          {menuOpen ? (
            <div
              ref={panelRef}
              id={panelId}
              className="chat-header__menu-panel"
              role="group"
              aria-label={t("chat.header.threadActions")}
            >
              <p className="mono-label">{t("chat.header.context")}</p>
              {contextActions}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}

/**
 * The conversation title: plain text for a new or archived thread, otherwise a
 * button that turns into a text field. Enter or blur saves, Escape cancels and
 * returns focus to the title.
 */
function ConversationTitle({
  title,
  editable,
  onRename,
}: {
  readonly title: string;
  readonly editable: boolean;
  readonly onRename: (title: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(title);
  const [saving, setSaving] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.select();
    }
  }, [editing]);

  if (!editable) {
    return <span className="chat-header__title-text">{title}</span>;
  }

  const finish = (refocus: boolean) => {
    setEditing(false);
    if (refocus) {
      window.requestAnimationFrame(() => buttonRef.current?.focus());
    }
  };

  const save = async (refocus: boolean) => {
    const next = value.trim();
    if (saving) {
      return;
    }
    if (next.length === 0 || next === title) {
      setValue(title);
      finish(refocus);
      return;
    }
    setSaving(true);
    try {
      await onRename(next);
      finish(refocus);
    } catch {
      // The page reports the failure; keep the field open for another try.
    } finally {
      setSaving(false);
    }
  };

  const handleKey = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void save(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setValue(title);
      finish(true);
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="chat-header__title-input"
        value={value}
        maxLength={200}
        disabled={saving}
        aria-label={t("chat.header.titleInput")}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKey}
        onBlur={() => void save(false)}
      />
    );
  }

  return (
    <button
      ref={buttonRef}
      type="button"
      className="chat-header__title-button"
      onClick={() => {
        setValue(title);
        setEditing(true);
      }}
      aria-label={t("chat.header.renameTitle", { title })}
      title={t("chat.header.renameHint")}
    >
      <span className="chat-header__title-text">{title}</span>
      <Icon name="pencil" size={11} />
    </button>
  );
}
