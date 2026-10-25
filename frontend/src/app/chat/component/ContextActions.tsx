import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../../apis/fetch-client";
import { buttonClassName } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n, type Translate, translateApiError } from "../../i18n";
import {
  useClearAgentConversation,
  useCompactAgentConversation,
} from "../../generated-apis-types/agent/agent";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { invalidateConversation } from "../query";

interface ContextActionsProps {
  readonly conversationId: number | null;
  readonly streaming: boolean;
  readonly archived: boolean;
  readonly disabled?: boolean;
  readonly className?: string;
  /** Lets a surface merge the boundary entry before the refetch lands. */
  readonly onApplied?: (entry: AgentEntrySchema) => void;
}

function describeContextError(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    if (error.code === "agent_conversation_busy") {
      return t("chat.contextActions.busy");
    }
    if (error.code === "agent_conversation_archived") {
      return t("chat.contextActions.archived");
    }
    return translateApiError(error, t, "chat.contextActions.fallback");
  }
  if (error instanceof Error && error.message.length > 0) {
    return error.message;
  }
  return t("chat.contextActions.fallback");
}

function shouldRefetch(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 409 ||
      error.code === "agent_conversation_busy" ||
      error.code === "agent_conversation_archived")
  );
}

/**
 * Compact and clear controls for one conversation's active context.
 *
 * Compact is a single calm action because it only folds earlier turns into a
 * summary. Clear asks for one inline confirmation because it changes what the
 * model sees, even though every transcript entry stays readable.
 */
export function ContextActions({
  conversationId,
  streaming,
  archived,
  disabled = false,
  className,
  onApplied,
}: ContextActionsProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const compactConversation = useCompactAgentConversation();
  const clearConversation = useClearAgentConversation();
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clearTriggerRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef(false);
  const inFlightRef = useRef(false);

  const contextBlocked =
    conversationId === null || archived || streaming || disabled;
  const pending = compactConversation.isPending || clearConversation.isPending;
  const blocked = contextBlocked || pending;

  useEffect(() => {
    if (confirmingClear) {
      cancelRef.current?.focus();
      return;
    }
    if (restoreFocusRef.current) {
      restoreFocusRef.current = false;
      clearTriggerRef.current?.focus();
    }
  }, [confirmingClear]);

  const cancelClear = () => {
    restoreFocusRef.current = true;
    setConfirmingClear(false);
  };

  const applyBoundary = async (kind: "compact" | "clear") => {
    if (conversationId === null || blocked || inFlightRef.current) {
      return;
    }
    setError(null);
    inFlightRef.current = true;
    try {
      const entry =
        kind === "compact"
          ? await compactConversation.mutateAsync({ conversationId })
          : await clearConversation.mutateAsync({ conversationId });
      setConfirmingClear(false);
      onApplied?.(entry);
      await invalidateConversation(queryClient, conversationId);
      toast.success(
        kind === "compact"
          ? t("chat.contextActions.compacted")
          : t("chat.contextActions.cleared"),
      );
    } catch (caught) {
      setError(describeContextError(caught, t));
      if (shouldRefetch(caught)) {
        void invalidateConversation(queryClient, conversationId);
      }
    } finally {
      inFlightRef.current = false;
    }
  };

  const rootClassName = ["context-actions", className]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={rootClassName}
      role="group"
      aria-label={t("chat.contextActions.groupAria")}
      aria-busy={pending}
    >
      {confirmingClear ? (
        <div
          className="context-actions__confirm"
          role="group"
          aria-label={t("chat.contextActions.confirmAria")}
        >
          <span className="context-actions__question">
            {t("chat.contextActions.confirmQuestion")}
          </span>
          <button
            ref={cancelRef}
            type="button"
            className={buttonClassName({ variant: "ghost", size: "sm" })}
            onClick={cancelClear}
            data-context-cancel
          >
            {t("chat.contextActions.cancel")}
          </button>
          <button
            type="button"
            className={buttonClassName({ variant: "ink", size: "sm" })}
            onClick={() => void applyBoundary("clear")}
            disabled={blocked}
            aria-label={t("chat.contextActions.confirmClearAria")}
          >
            {clearConversation.isPending
              ? t("chat.contextActions.clearing")
              : t("chat.contextActions.clear")}
          </button>
        </div>
      ) : (
        <>
          <button
            type="button"
            className={buttonClassName({ variant: "ghost", size: "sm" })}
            onClick={() => void applyBoundary("compact")}
            disabled={blocked}
            title={t("chat.contextActions.compactTitle")}
            aria-label={t("chat.contextActions.compactAria")}
          >
            <Icon name="layers" size={14} />
            {compactConversation.isPending
              ? t("chat.contextActions.compacting")
              : t("chat.contextActions.compact")}
          </button>
          <button
            ref={clearTriggerRef}
            type="button"
            className={buttonClassName({ variant: "ghost", size: "sm" })}
            onClick={() => {
              setError(null);
              setConfirmingClear(true);
            }}
            disabled={blocked}
            title={t("chat.contextActions.clearTitle")}
            aria-label={t("chat.contextActions.clearAria")}
          >
            <Icon name="archive" size={14} />
            {t("chat.contextActions.clear")}
          </button>
        </>
      )}
      {error ? (
        <p className="context-actions__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
