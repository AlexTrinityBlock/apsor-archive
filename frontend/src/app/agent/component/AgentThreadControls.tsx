import { useId } from "react";
import { Link } from "react-router-dom";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { ContextActions } from "../../chat/component/ContextActions";
import type {
  AgentConversationSchema,
  AgentEntrySchema,
} from "../../generated-apis-types/schemas";

interface AgentThreadControlsProps {
  readonly conversations: readonly AgentConversationSchema[];
  readonly selectedId: number | null;
  readonly loading: boolean;
  readonly streaming: boolean;
  readonly archived: boolean;
  readonly disabled: boolean;
  readonly onSelect: (id: number | null) => void;
  readonly onNew: () => void;
  readonly onContextApplied: (entry: AgentEntrySchema) => void;
}

/** Thread picker, new-thread action, and the full-desk handoff. */
export function AgentThreadControls({
  conversations,
  selectedId,
  loading,
  streaming,
  archived,
  disabled,
  onSelect,
  onNew,
  onContextApplied,
}: AgentThreadControlsProps) {
  const selectId = useId();
  const active = conversations.filter((conversation) => conversation.status === "active");
  const archivedThreads = conversations.filter(
    (conversation) => conversation.status === "archived",
  );

  return (
    <div className="pi-agent-controls">
      <div className="pi-agent-controls__row">
        <label className="visually-hidden" htmlFor={selectId}>
          Conversation thread
        </label>
        <select
          id={selectId}
          className="pi-agent-controls__select"
          value={selectedId ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            onSelect(value.length === 0 ? null : Number(value));
          }}
          disabled={loading}
        >
          <option value="">New thread</option>
          {active.length > 0 ? (
            <optgroup label="Active threads">
              {active.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title}
                </option>
              ))}
            </optgroup>
          ) : null}
          {archivedThreads.length > 0 ? (
            <optgroup label="Archived">
              {archivedThreads.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title} · archived
                </option>
              ))}
            </optgroup>
          ) : null}
        </select>

        <Button
          variant="ghost"
          size="sm"
          onClick={onNew}
          iconOnly
          aria-label="New conversation"
        >
          <Icon name="plus" size={15} />
        </Button>

        <ButtonLink
          to={selectedId === null ? "/chat" : `/chat/${selectedId}`}
          variant="ghost"
          size="sm"
          className="pi-agent-controls__desk"
          aria-label="Open the full correspondence desk"
        >
          <Icon name="external" size={14} />
          <span>Full desk</span>
        </ButtonLink>
      </div>

      <ContextActions
        key={`${selectedId ?? "new"}:${archived ? "archived" : "active"}`}
        conversationId={selectedId}
        streaming={streaming}
        archived={archived}
        disabled={disabled}
        className="context-actions--dock"
        onApplied={onContextApplied}
      />
    </div>
  );
}

/** A small decorative seal link used in the header copy. */
export function AgentDeskLink({ conversationId }: { readonly conversationId: number | null }) {
  return (
    <Link
      className="pi-agent-desk-link"
      to={conversationId === null ? "/chat" : `/chat/${conversationId}`}
    >
      Full desk
      <Icon name="arrow-up-right" size={12} />
    </Link>
  );
}
