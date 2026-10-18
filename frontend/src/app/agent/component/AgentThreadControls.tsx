import { useId } from "react";
import { Link } from "react-router-dom";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import type { AgentConversationSchema } from "../../generated-apis-types/schemas";

interface AgentThreadControlsProps {
  readonly conversations: readonly AgentConversationSchema[];
  readonly selectedId: number | null;
  readonly loading: boolean;
  readonly onSelect: (id: number | null) => void;
  readonly onNew: () => void;
}

/** Thread picker, new-thread action, and the full-desk handoff. */
export function AgentThreadControls({
  conversations,
  selectedId,
  loading,
  onSelect,
  onNew,
}: AgentThreadControlsProps) {
  const selectId = useId();
  const active = conversations.filter((conversation) => conversation.status === "active");
  const archived = conversations.filter((conversation) => conversation.status === "archived");

  return (
    <div className="pi-agent-controls">
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
        {archived.length > 0 ? (
          <optgroup label="Archived">
            {archived.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title} · archived
              </option>
            ))}
          </optgroup>
        ) : null}
      </select>

      <Button variant="ghost" size="sm" onClick={onNew} iconOnly aria-label="New conversation">
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
