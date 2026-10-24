import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { formatRelative } from "../../../lib/format";
import type { AgentApprovalSchema } from "../../generated-apis-types/schemas";
import { isRecord, numberValue, stringValue } from "../types";

interface ApprovalStackProps {
  readonly approvals: readonly AgentApprovalSchema[];
  readonly disabled?: boolean;
  readonly archived?: boolean;
  readonly onResolve: (
    approvalId: number,
    decision: "approve" | "reject",
  ) => Promise<boolean>;
}

interface ApprovalPreview {
  readonly content: string;
  readonly supersedes: readonly number[];
  readonly occurredAt: string | null;
  readonly risk: string | null;
  readonly contentChars: number | null;
}

function readPreview(approval: AgentApprovalSchema): ApprovalPreview {
  const preview = isRecord(approval.preview) ? approval.preview : {};
  const rawSupersedes = preview.supersedes;
  const supersedes = Array.isArray(rawSupersedes)
    ? rawSupersedes.flatMap((item) => {
        const value = numberValue(item);
        return value === null ? [] : [value];
      })
    : [];
  return {
    content: stringValue(preview.content) ?? "",
    supersedes,
    occurredAt: stringValue(preview.occurred_at),
    risk: stringValue(preview.risk),
    contentChars: numberValue(preview.content_chars),
  };
}

function ApprovalCard({
  approval,
  disabled,
  archived,
  resolving,
  onResolve,
}: {
  readonly approval: AgentApprovalSchema;
  readonly disabled: boolean;
  readonly archived: boolean;
  readonly resolving: "approve" | "reject" | null;
  readonly onResolve: (decision: "approve" | "reject") => void;
}) {
  const preview = readPreview(approval);
  const busy = resolving !== null;
  const blocked = disabled || archived || busy;

  return (
    <section
      className="chat-approval"
      role="group"
      aria-label="Memory write approval"
    >
      <header className="chat-approval__head">
        <span className="chat-approval__mark" aria-hidden="true">
          <Icon name="memory" size={18} />
        </span>
        <div className="chat-approval__heading">
          <p className="eyebrow">Human approval required</p>
          <h3>The agent wants to write a memory.</h3>
        </div>
        <Badge tone="ochre">Pending</Badge>
      </header>

      <div className="chat-approval__body">
        <p className="chat-approval__label">Proposed memory</p>
        <pre className="chat-approval__content">{preview.content}</pre>

        <dl className="chat-approval__meta">
          <div>
            <dt>Tool</dt>
            <dd>{approval.tool_name}</dd>
          </div>
          <div>
            <dt>Supersedes</dt>
            <dd>
              {preview.supersedes.length > 0
                ? preview.supersedes.map((id) => `#${id}`).join(", ")
                : "No existing memory"}
            </dd>
          </div>
          <div>
            <dt>Occurred</dt>
            <dd>{preview.occurredAt ?? "Now"}</dd>
          </div>
          <div>
            <dt>Requested</dt>
            <dd>{formatRelative(approval.requested_at)}</dd>
          </div>
        </dl>

        <p className="chat-approval__risk">
          <Icon name="info" size={14} />
          {preview.risk ??
            "Approving appends a durable memory. Rejecting writes nothing."}
        </p>

        {preview.contentChars !== null && preview.contentChars > 0 ? (
          <p className="chat-approval__count">
            {preview.contentChars.toLocaleString()} characters will be stored.
          </p>
        ) : null}
      </div>

      {archived ? (
        <p className="chat-approval__notice" role="status">
          This thread is archived. Restore it before resolving the write.
        </p>
      ) : null}

      <footer className="chat-approval__actions">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onResolve("reject")}
          disabled={blocked}
          aria-label={`Reject saving memory for approval ${approval.id}`}
        >
          {resolving === "reject" ? (
            <Loader size={14} label="Rejecting the memory write" />
          ) : (
            <Icon name="close" size={14} />
          )}
          {resolving === "reject" ? "Rejecting…" : "Reject"}
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={() => onResolve("approve")}
          disabled={blocked}
          aria-label={`Approve saving memory for approval ${approval.id}`}
        >
          {resolving === "approve" ? (
            <Loader size={14} label="Saving the memory" />
          ) : (
            <Icon name="check" size={14} />
          )}
          {resolving === "approve" ? "Saving…" : "Approve write"}
        </Button>
      </footer>
    </section>
  );
}

/**
 * Persisted approval cards for the chat stream.
 *
 * The cards come from the durable approvals endpoint, so they reappear after a
 * reload while the run is waiting. Resolution streams the resumed turn through
 * the parent hook; a duplicate resolution returns a clear 409.
 */
export function ApprovalStack({
  approvals,
  disabled = false,
  archived = false,
  onResolve,
}: ApprovalStackProps) {
  const [resolving, setResolving] = useState<{
    readonly id: number;
    readonly decision: "approve" | "reject";
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (approvals.length === 0) {
    return null;
  }

  const resolve = async (
    approval: AgentApprovalSchema,
    decision: "approve" | "reject",
  ) => {
    if (resolving !== null) {
      return;
    }
    setError(null);
    setResolving({ id: approval.id, decision });
    const ok = await onResolve(approval.id, decision);
    if (!ok) {
      setError(
        "The approval could not be resolved. Refresh the thread and try again.",
      );
    }
    setResolving(null);
  };

  return (
    <div className="chat-approvals" aria-live="polite">
      {approvals.map((approval) => (
        <ApprovalCard
          key={approval.id}
          approval={approval}
          disabled={disabled}
          archived={archived}
          resolving={resolving?.id === approval.id ? resolving.decision : null}
          onResolve={(decision) => void resolve(approval, decision)}
        />
      ))}
      {error ? (
        <p className="chat-approval__error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}
    </div>
  );
}
