import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useI18n, type Translate } from "../../i18n";
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
  const { t, formatDateTime, formatRelative, formatNumber } = useI18n();
  const targets =
    preview.supersedes.length > 0
      ? preview.supersedes.map((id) => `#${id}`).join(", ")
      : t("chat.approval.noExistingMemory");
  return (
    <div className="chat-approval__body">
      {deprecating ? (
        <>
          <p className="chat-approval__label">
            {t("chat.approval.deprecateLabel")}
          </p>
          <p className="chat-approval__deprecate-ids">
            {preview.supersedes.length > 0
              ? preview.supersedes
                  .map((id) => t("chat.approval.crystalId", { id }))
                  .join(", ")
              : t("chat.approval.noMemoryId")}
          </p>
          {preview.reason ? (
            <p className="chat-approval__reason">
              <span>{t("chat.approval.reason")}</span>
              {preview.reason}
            </p>
          ) : null}
        </>
      ) : (
        <>
          <p className="chat-approval__label">
            {t("chat.approval.proposedMemory")}
          </p>
          <pre className="chat-approval__content">{preview.content}</pre>
        </>
      )}

      <dl className="chat-approval__meta">
        <div>
          <dt>{t("chat.approval.tool")}</dt>
          <dd>{approval.tool_name}</dd>
        </div>
        <div>
          <dt>
            {deprecating
              ? t("chat.approval.targets")
              : t("chat.approval.supersedes")}
          </dt>
          <dd>{targets}</dd>
        </div>
        {deprecating ? null : (
          <div>
            <dt>{t("chat.approval.occurred")}</dt>
            <dd>
              {preview.occurredAt
                ? formatDateTime(preview.occurredAt)
                : t("chat.approval.now")}
            </dd>
          </div>
        )}
        <div>
          <dt>{t("chat.approval.requested")}</dt>
          <dd>{formatRelative(approval.requested_at)}</dd>
        </div>
      </dl>

      <p className="chat-approval__risk">
        <Icon name="info" size={14} />
        {preview.risk ??
          (deprecating
            ? t("chat.approval.riskDeprecate")
            : t("chat.approval.riskSave"))}
      </p>

      {!deprecating && preview.contentChars !== null && preview.contentChars > 0 ? (
        <p className="chat-approval__count">
          {t(
            preview.contentChars === 1
              ? "chat.approval.charactersStoredOne"
              : "chat.approval.charactersStoredOther",
            { count: formatNumber(preview.contentChars) },
          )}
        </p>
      ) : null}
    </div>
  );
}

function approveText(
  resolving: "approve" | "reject" | null,
  deprecating: boolean,
  t: Translate,
): string {
  if (resolving === "approve") {
    return deprecating
      ? t("chat.approval.deprecating")
      : t("chat.approval.saving");
  }
  return deprecating
    ? t("chat.approval.approveDeprecation")
    : t("chat.approval.approveWrite");
}

function approveAria(
  approvalId: number,
  deprecating: boolean,
  t: Translate,
): string {
  return deprecating
    ? t("chat.approval.approveDeprecationAria", { id: approvalId })
    : t("chat.approval.approveWriteAria", { id: approvalId });
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
  const { t } = useI18n();
  const preview = readPreview(approval);
  const deprecating = preview.mode === "deprecate";
  const busy = resolving !== null;
  const blocked = disabled || archived || busy;

  return (
    <section
      className="chat-approval"
      role="group"
      aria-label={
        deprecating
          ? t("chat.approval.deprecationAria")
          : t("chat.approval.writeAria")
      }
    >
      <header className="chat-approval__head">
        <span className="chat-approval__mark" aria-hidden="true">
          <Icon name={deprecating ? "history" : "memory"} size={18} />
        </span>
        <div className="chat-approval__heading">
          <p className="eyebrow">{t("chat.approval.eyebrow")}</p>
          <h3>
            {deprecating
              ? t("chat.approval.deprecateTitle")
              : t("chat.approval.writeTitle")}
          </h3>
        </div>
        <Badge tone="ochre">{t("chat.approval.pending")}</Badge>
      </header>

      <ApprovalBody
        approval={approval}
        preview={preview}
        deprecating={deprecating}
      />

      {archived ? (
        <p className="chat-approval__notice" role="status">
          {t("chat.approval.archived")}
        </p>
      ) : null}

      <footer className="chat-approval__actions">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onResolve("reject")}
          disabled={blocked}
          aria-label={t("chat.approval.rejectAria", { id: approval.id })}
        >
          {resolving === "reject" ? (
            <Loader size={14} label={t("chat.approval.rejectingLabel")} />
          ) : (
            <Icon name="close" size={14} />
          )}
          {resolving === "reject"
            ? t("chat.approval.rejecting")
            : t("chat.approval.reject")}
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={() => onResolve("approve")}
          disabled={blocked}
          aria-label={approveAria(approval.id, deprecating, t)}
        >
          {resolving === "approve" ? (
            <Loader
              size={14}
              label={
                deprecating
                  ? t("chat.approval.deprecatingLabel")
                  : t("chat.approval.savingLabel")
              }
            />
          ) : (
            <Icon name={deprecating ? "history" : "check"} size={14} />
          )}
          {approveText(resolving, deprecating, t)}
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
  const { t } = useI18n();

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
      setError(t("chat.approval.resolveFailed"));
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
