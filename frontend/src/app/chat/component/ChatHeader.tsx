import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import type { AgentConversationDetailSchema } from "../../generated-apis-types/schemas";
import { formatRelative } from "../../../lib/format";
import { clearLastChatConversation } from "../session-storage";

export type ChatPane = "thread" | "inspector";

interface ChatHeaderProps {
  readonly conversation: AgentConversationDetailSchema | null;
  readonly conversationId: number | null;
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
          aria-label="Chats"
          title={drawerOpen ? "Hide conversations" : "Show conversations"}
        >
          <Icon name="menu" size={14} />
          <span>Chats</span>
        </button>

        <div className="chat-header__titles">
          <div className="chat-header__title-row">
            <h1>
              {conversation?.title ??
                (conversationId === null
                  ? "New conversation"
                  : `Conversation #${conversationId}`)}
            </h1>
            {archived ? <Badge tone="ochre">Archived</Badge> : null}
            {parentId !== null ? (
              <Link
                className="chat-header__fork"
                to={`/chat/${parentId}`}
                title="Open the parent conversation"
              >
                <Badge tone="neutral">Fork of #{parentId}</Badge>
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
                <span>{conversation.entries_total} entries</span>
                {updated ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>updated {formatRelative(updated)}</span>
                  </>
                ) : null}
              </>
            ) : (
              <span>Persistent transcript · tool steps · citations</span>
            )}
          </p>
        </div>
      </div>

      <div className="chat-header__actions">
        {narrow ? (
          <div className="chat-pane-tabs" role="tablist" aria-label="Chat panes">
            <button
              type="button"
              role="tab"
              aria-selected={pane === "thread"}
              className={pane === "thread" ? "is-active" : undefined}
              onClick={() => onPane("thread")}
            >
              Chat
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pane === "inspector"}
              className={pane === "inspector" ? "is-active" : undefined}
              onClick={() => onPane("inspector")}
            >
              Inspector
            </button>
          </div>
        ) : null}

        {!narrow && inspectorCollapsed ? (
          <Button
            variant="secondary"
            size="sm"
            aria-label="Open inspector"
            onClick={() => {
              setMenuOpen(false);
              onOpenInspector();
            }}
          >
            <Icon name="layers" size={13} />
            <span>Inspector</span>
          </Button>
        ) : null}

        <Button
          variant="ink"
          size="sm"
          aria-label="New chat"
          onClick={() => {
            setMenuOpen(false);
            clearLastChatConversation();
            onNew();
          }}
        >
          <Icon name="plus" size={13} />
          <span>New chat</span>
        </Button>

        <div className="chat-header__menu" ref={menuRef}>
          <button
            type="button"
            className="chat-icon-btn"
            onClick={() => setMenuOpen((value) => !value)}
            aria-label="Thread actions"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            title="Thread actions"
          >
            <span aria-hidden="true">⋯</span>
          </button>
          {menuOpen ? (
            <div
              className="chat-header__menu-panel"
              role="group"
              aria-label="Thread actions"
            >
              <p className="mono-label">Context</p>
              {contextActions}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
