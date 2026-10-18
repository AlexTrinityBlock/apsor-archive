import {
  memo,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../../apis/fetch-client";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useDeleteAgentConversation,
  useUpdateAgentConversation,
} from "../../generated-apis-types/agent/agent";
import type { AgentConversationSchema } from "../../generated-apis-types/schemas";
import { formatRelative } from "../../../lib/format";
import {
  invalidateConversationDetail,
  invalidateConversationList,
} from "../query";

interface ConversationRailProps {
  readonly conversations: readonly AgentConversationSchema[];
  readonly loading: boolean;
  readonly error: unknown;
  readonly activeId: number | null;
  readonly open: boolean;
  readonly onRetry: () => void;
  readonly onNew: () => void;
  readonly onClose: () => void;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return "The thread list could not be read.";
}

interface RailItemProps {
  readonly conversation: AgentConversationSchema;
  readonly active: boolean;
  readonly editing: boolean;
  readonly title: string;
  readonly busy: boolean;
  readonly confirmingDelete: boolean;
  readonly onTitleChange: (value: string) => void;
  readonly onEdit: () => void;
  readonly onCancelEdit: () => void;
  readonly onSaveTitle: () => void;
  readonly onToggleStatus: () => void;
  readonly onRequestDelete: () => void;
  readonly onCancelDelete: () => void;
  readonly onDelete: () => void;
  readonly onClose: () => void;
}

function RailItem({
  conversation,
  active,
  editing,
  title,
  busy,
  confirmingDelete,
  onTitleChange,
  onEdit,
  onCancelEdit,
  onSaveTitle,
  onToggleStatus,
  onRequestDelete,
  onCancelDelete,
  onDelete,
  onClose,
}: RailItemProps) {
  const archived = conversation.status === "archived";
  const inputId = `chat-rail-title-${conversation.id}`;

  const handleTitleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSaveTitle();
  };

  return (
    <li
      className={[
        "chat-thread-link",
        active ? "is-active" : null,
        archived ? "is-archived" : null,
        busy ? "is-busy" : null,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {editing ? (
        <form className="chat-thread-link__edit" onSubmit={handleTitleSubmit}>
          <label className="visually-hidden" htmlFor={inputId}>
            Thread title
          </label>
          <input
            id={inputId}
            value={title}
            onChange={(event) => onTitleChange(event.target.value)}
            maxLength={200}
            autoFocus
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                onCancelEdit();
              }
            }}
          />
          <div className="chat-thread-link__edit-actions">
            <Button type="submit" size="sm" variant="ink" disabled={busy}>
              Save
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={onCancelEdit}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <Link
          className="chat-thread-link__anchor"
          to={`/chat/${conversation.id}`}
          onClick={onClose}
          aria-current={active ? "page" : undefined}
        >
          <span className="chat-thread-link__title">{conversation.title}</span>
          <span className="chat-thread-link__meta">
            <span>{formatRelative(conversation.last_entry_at ?? conversation.created_at)}</span>
            <span aria-hidden="true">·</span>
            <span>{conversation.model}</span>
            {archived ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="chat-thread-link__archived">archived</span>
              </>
            ) : null}
          </span>
        </Link>
      )}

      {!editing && !confirmingDelete ? (
        <div className="chat-thread-link__actions">
          <button
            type="button"
            className="chat-thread-link__action"
            onClick={onEdit}
            aria-label={`Rename ${conversation.title}`}
            title="Rename"
            disabled={busy}
          >
            <Icon name="pencil" size={13} />
          </button>
          <button
            type="button"
            className="chat-thread-link__action"
            onClick={onToggleStatus}
            aria-label={
              archived
                ? `Restore ${conversation.title}`
                : `Archive ${conversation.title}`
            }
            title={archived ? "Restore" : "Archive"}
            disabled={busy}
          >
            <Icon name={archived ? "history" : "archive"} size={13} />
          </button>
          <button
            type="button"
            className="chat-thread-link__action chat-thread-link__action--danger"
            onClick={onRequestDelete}
            aria-label={`Delete ${conversation.title}`}
            title="Delete"
            disabled={busy}
          >
            <Icon name="trash" size={13} />
          </button>
        </div>
      ) : null}

      {confirmingDelete ? (
        <div className="chat-thread-link__confirm" role="alert">
          <p>Remove this thread from the desk?</p>
          <div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="chat-thread-link__delete"
              onClick={onDelete}
              disabled={busy}
            >
              Remove
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={onCancelDelete}>
              Keep
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

/** Thread rail: list, create, rename, archive/restore, and remove. */
export const ConversationRail = memo(function ConversationRail({
  conversations,
  loading,
  error,
  activeId,
  open,
  onRetry,
  onNew,
  onClose,
}: ConversationRailProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const updateConversation = useUpdateAgentConversation();
  const deleteConversation = useDeleteAgentConversation();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const active = useMemo(
    () => conversations.filter((conversation) => conversation.status === "active"),
    [conversations],
  );
  const archived = useMemo(
    () =>
      conversations.filter((conversation) => conversation.status === "archived"),
    [conversations],
  );

  const refresh = async (conversationId?: number) => {
    await Promise.all([
      invalidateConversationList(queryClient),
      conversationId === undefined
        ? Promise.resolve()
        : invalidateConversationDetail(queryClient, conversationId),
    ]);
  };

  const startRename = (conversation: AgentConversationSchema) => {
    setPendingDeleteId(null);
    setEditingId(conversation.id);
    setEditTitle(conversation.title);
  };

  const saveTitle = async (conversation: AgentConversationSchema) => {
    if (busyId !== null) {
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
      toast.success("Thread renamed.");
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  const toggleStatus = async (conversation: AgentConversationSchema) => {
    if (busyId !== null) {
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
        nextStatus === "archived" ? "Thread archived." : "Thread restored.",
      );
      if (nextStatus === "archived" && activeId === conversation.id) {
        navigate("/chat");
        onClose();
      }
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  const removeConversation = async (conversation: AgentConversationSchema) => {
    if (busyId !== null) {
      return;
    }
    setBusyId(conversation.id);
    try {
      await deleteConversation.mutateAsync({
        conversationId: conversation.id,
      });
      await refresh();
      setPendingDeleteId(null);
      toast.success("Thread removed from the desk.");
      if (activeId === conversation.id) {
        navigate("/chat");
        onClose();
      }
    } catch (caught) {
      toast.error(describeError(caught));
    } finally {
      setBusyId(null);
    }
  };

  const renderItem = (conversation: AgentConversationSchema) => (
    <RailItem
      key={conversation.id}
      conversation={conversation}
      active={conversation.id === activeId}
      editing={editingId === conversation.id}
      title={editTitle}
      busy={busyId === conversation.id}
      confirmingDelete={pendingDeleteId === conversation.id}
      onTitleChange={setEditTitle}
      onEdit={() => startRename(conversation)}
      onCancelEdit={() => setEditingId(null)}
      onSaveTitle={() => {
        void saveTitle(conversation);
      }}
      onToggleStatus={() => {
        void toggleStatus(conversation);
      }}
      onRequestDelete={() => {
        setEditingId(null);
        setPendingDeleteId(conversation.id);
      }}
      onCancelDelete={() => setPendingDeleteId(null)}
      onDelete={() => {
        void removeConversation(conversation);
      }}
      onClose={onClose}
    />
  );

  let railBody: ReactNode;
  if (loading) {
    railBody = (
      <div className="chat-rail__loading">
        <Loader size={28} label="Reading the thread list" />
        <span>Reading the desk…</span>
      </div>
    );
  } else if (error) {
    railBody = (
      <div className="chat-rail__error" role="alert">
        <p>{describeError(error)}</p>
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      </div>
    );
  } else if (conversations.length === 0) {
    railBody = (
      <div className="chat-rail__empty">
        <p className="eyebrow">No sheets yet</p>
        <p>The first question opens a thread and keeps its sources.</p>
      </div>
    );
  } else {
    railBody = (
      <>
        <section className="chat-rail__section">
          <p className="chat-rail__section-label">Active</p>
          {active.length === 0 ? (
            <p className="chat-rail__section-empty">
              Every thread is archived.
            </p>
          ) : (
            <ul className="chat-rail__list">{active.map(renderItem)}</ul>
          )}
        </section>

        {archived.length > 0 ? (
          <details className="chat-rail__archived">
            <summary>
              <span>Archived</span>
              <span className="chat-rail__archived-count">{archived.length}</span>
              <Icon name="chevron-down" size={13} />
            </summary>
            <ul className="chat-rail__list">{archived.map(renderItem)}</ul>
          </details>
        ) : null}
      </>
    );
  }

  return (
    <>
      {open ? (
        <button
          type="button"
          className="chat-rail__scrim"
          onClick={onClose}
          aria-label="Close threads"
        />
      ) : null}
      <aside
        id="chat-thread-rail"
        className={open ? "chat-rail is-open" : "chat-rail"}
        aria-label="Conversation threads"
      >
        <div className="chat-rail__inner">
          <header className="chat-rail__head">
            <div>
              <p className="eyebrow">Reading room</p>
              <h2>Threads</h2>
              <p className="chat-rail__count">
                {loading
                  ? "reading the desk…"
                  : `${active.length} active · ${archived.length} archived`}
              </p>
            </div>
            <button
              type="button"
              className="chat-rail__close"
              onClick={onClose}
              aria-label="Close threads"
            >
              <Icon name="close" size={16} />
            </button>
          </header>

          <Button
            variant="primary"
            size="sm"
            block
            className="chat-rail__new"
            onClick={() => {
              setEditingId(null);
              setPendingDeleteId(null);
              onNew();
            }}
          >
            <Icon name="plus" size={14} />
            New conversation
          </Button>

          <div className="chat-rail__scroll">{railBody}</div>

          <footer className="chat-rail__foot">
            <Icon name="history" size={13} />
            <span>Entries are append-only. A thread keeps its frozen method.</span>
          </footer>
        </div>
      </aside>
    </>
  );
});
