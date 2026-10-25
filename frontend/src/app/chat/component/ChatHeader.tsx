import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import type { AgentConversationDetailSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { clearLastChatConversation } from "../session-storage";

export type ChatPane = "thread" | "inspector";

interface ChatHeaderProps {
  readonly conversation: AgentConversationDetailSchema | null;
  readonly conversationId: number | null;
  readonly transcript: string;
  readonly archived: boolean;
  readonly drawerOpen: boolean;
  readonly narrow: boolean;
  readonly pane: ChatPane;
  readonly inspectorCollapsed: boolean;
  readonly onToggleDrawer: () => void;
  readonly onPane: (pane: ChatPane) => void;
  readonly onOpenInspector: () => void;
  readonly onNew: () => void;
  readonly contextActions: ReactNode;
}

/** The slim chat header: drawer, title, compact meta, and overflow actions. */
export function ChatHeader({
  conversation,
  conversationId,
  transcript,
  archived,
  drawerOpen,
  narrow,
  pane,
  inspectorCollapsed,
  onToggleDrawer,
  onPane,
  onOpenInspector,
  onNew,
  contextActions,
}: ChatHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
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
        setMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [menuOpen]);

  const updated = conversation
    ? conversation.last_entry_at ?? conversation.created_at
    : null;
  const parentId = conversation?.parent_conversation_id ?? null;

  return (
    <header className="chat-header">
      <div className="chat-header__left">
        <button
          type="button"
          className="chat-header__drawer"
          onClick={onToggleDrawer}
          aria-expanded={drawerOpen}
          aria-controls="chat-sessions"
          aria-label={t("chat.header.chats")}
          title={
            drawerOpen
              ? t("chat.header.hideConversations")
              : t("chat.header.showConversations")
          }
        >
          <Icon name="menu" size={14} />
          <span>{t("chat.header.chats")}</span>
        </button>

        <div className="chat-header__titles">
          <div className="chat-header__title-row">
            <h1>
              {conversation?.title ??
                (conversationId === null
                  ? t("chat.header.newConversation")
                  : t("chat.header.conversation", { id: conversationId }))}
            </h1>
            {archived ? (
              <Badge tone="ochre">{t("chat.header.archived")}</Badge>
            ) : null}
            {parentId !== null ? (
              <Link
                className="chat-header__fork"
                to={`/chat/${parentId}`}
                title={t("chat.header.openParent")}
              >
                <Badge tone="neutral">
                  {t("chat.header.forkOf", { id: parentId })}
                </Badge>
              </Link>
            ) : null}
          </div>
          <p className="chat-header__meta">
            {conversation ? (
              <>
                <span>{conversation.provider}</span>
                <span aria-hidden="true">·</span>
                <span>{conversation.model}</span>
                <span aria-hidden="true">·</span>
                <span>
                  {t(
                    conversation.entries_total === 1
                      ? "chat.common.entryOne"
                      : "chat.common.entryOther",
                    { count: formatNumber(conversation.entries_total) },
                  )}
                </span>
                {updated ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>
                      {t("chat.common.updatedAt", {
                        time: formatRelative(updated),
                      })}
                    </span>
                  </>
                ) : null}
              </>
            ) : (
              <span>{t("chat.header.placeholder")}</span>
            )}
          </p>
        </div>
      </div>

      <div className="chat-header__actions">
        {narrow ? (
          <div
            className="chat-pane-tabs"
            role="tablist"
            aria-label={t("chat.header.panesAria")}
          >
            <button
              type="button"
              role="tab"
              aria-selected={pane === "thread"}
              className={pane === "thread" ? "is-active" : undefined}
              onClick={() => onPane("thread")}
            >
              {t("chat.header.chatTab")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pane === "inspector"}
              className={pane === "inspector" ? "is-active" : undefined}
              onClick={() => onPane("inspector")}
            >
              {t("chat.header.inspectorTab")}
            </button>
          </div>
        ) : null}

        {!narrow && inspectorCollapsed ? (
          <Button
            variant="secondary"
            size="sm"
            aria-label={t("chat.header.openInspector")}
            onClick={() => {
              setMenuOpen(false);
              onOpenInspector();
            }}
          >
            <Icon name="layers" size={13} />
            <span>{t("chat.header.inspectorTab")}</span>
          </Button>
        ) : null}

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
            type="button"
            className="chat-icon-btn"
            onClick={() => setMenuOpen((value) => !value)}
            aria-label={t("chat.header.threadActions")}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            title={t("chat.header.threadActions")}
          >
            <span aria-hidden="true">⋯</span>
          </button>
          {menuOpen ? (
            <div
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
