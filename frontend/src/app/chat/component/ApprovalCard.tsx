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
  readonly mode: "save" | "deprecate";
  readonly content: string;
  readonly supersedes: readonly number[];
  readonly reason: string | null;
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
    mode: stringValue(preview.mode) === "deprecate" ? "deprecate" : "save",
    content: stringValue(preview.content) ?? "",
    supersedes,
    reason: stringValue(preview.reason),
    occurredAt: stringValue(preview.occurred_at),
    risk: stringValue(preview.risk),
    contentChars: numberValue(preview.content_chars),
  };
}

function ApprovalBody({
  approval,
  preview,
  deprecating,
}: {
  readonly approval: AgentApprovalSchema;
  readonly preview: ApprovalPreview;
  readonly deprecating: boolean;
}) {
  const targets =
    preview.supersedes.length > 0
      ? preview.supersedes.map((id) => `#${id}`).join(", ")
      : "No existing memory";
  return (
    <div className="chat-approval__body">
      {deprecating ? (
        <>
          <p className="chat-approval__label">Memories to deprecate</p>
          <p className="chat-approval__deprecate-ids">
            {preview.supersedes.length > 0
              ? preview.supersedes.map((id) => `CRYSTAL #${id}`).join(", ")
              : "No memory id supplied"}
          </p>
          {preview.reason ? (
            <p className="chat-approval__reason">
              <span>Reason</span>
              {preview.reason}
            </p>
          ) : null}
        </>
      ) : (
        <>
          <p className="chat-approval__label">Proposed memory</p>
          <pre className="chat-approval__content">{preview.content}</pre>
        </>
      )}

      <dl className="chat-approval__meta">
        <div>
          <dt>Tool</dt>
          <dd>{approval.tool_name}</dd>
        </div>
        <div>
          <dt>{deprecating ? "Targets" : "Supersedes"}</dt>
          <dd>{targets}</dd>
        </div>
        {deprecating ? null : (
          <div>
            <dt>Occurred</dt>
            <dd>{preview.occurredAt ?? "Now"}</dd>
          </div>
        )}
        <div>
          <dt>Requested</dt>
          <dd>{formatRelative(approval.requested_at)}</dd>
        </div>
      </dl>

      <p className="chat-approval__risk">
        <Icon name="info" size={14} />
        {preview.risk ??
          (deprecating
            ? "Approving retires the records without writing a replacement."
            : "Approving appends a durable memory. Rejecting writes nothing.")}
      </p>

      {!deprecating && preview.contentChars !== null && preview.contentChars > 0 ? (
        <p className="chat-approval__count">
          {preview.contentChars.toLocaleString()} characters will be stored.
        </p>
      ) : null}
    </div>
  );
}

function approveText(resolving: "approve" | "reject" | null, deprecating: boolean): string {
  if (resolving === "approve") {
    return deprecating ? "Deprecating…" : "Saving…";
  }
  return deprecating ? "Approve deprecation" : "Approve write";
}

function approveAria(approvalId: number, deprecating: boolean): string {
  return deprecating
    ? `Approve deprecating memories for approval ${approvalId}`
    : `Approve saving memory for approval ${approvalId}`;
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
  const deprecating = preview.mode === "deprecate";
  const busy = resolving !== null;
  const blocked = disabled || archived || busy;

  return (
    <section
      className="chat-approval"
      role="group"
      aria-label={
        deprecating ? "Memory deprecation approval" : "Memory write approval"
      }
    >
      <header className="chat-approval__head">
        <span className="chat-approval__mark" aria-hidden="true">
          <Icon name={deprecating ? "history" : "memory"} size={18} />
        </span>
        <div className="chat-approval__heading">
          <p className="eyebrow">Human approval required</p>
          <h3>
            {deprecating
              ? "The agent wants to deprecate memories."
              : "The agent wants to write a memory."}
          </h3>
        </div>
        <Badge tone="ochre">Pending</Badge>
      </header>

      <ApprovalBody
        approval={approval}
        preview={preview}
        deprecating={deprecating}
      />

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
          aria-label={`Reject the memory action for approval ${approval.id}`}
        >
          {resolving === "reject" ? (
            <Loader size={14} label="Rejecting the memory action" />
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
          aria-label={approveAria(approval.id, deprecating)}
        >
          {resolving === "approve" ? (
            <Loader
              size={14}
              label={deprecating ? "Deprecating the memories" : "Saving the memory"}
            />
          ) : (
            <Icon name={deprecating ? "history" : "check"} size={14} />
          )}
          {approveText(resolving, deprecating)}
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
