import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import {
  getGetEmbeddingBackfillStatusQueryKey,
  useGetEmbeddingBackfillStatus,
  useRetryEmbeddingBackfill,
} from "../../generated-apis-types";
import type { EmbeddingBackfillStatusSchema } from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";

/** Whether the card has anything worth telling root. */
export function hasBackfillNews(status: EmbeddingBackfillStatusSchema): boolean {
  return status.pending_chunks > 0 || status.abandoned_chunks > 0;
}

/**
 * Root-only line about passages whose text is indexed but whose embedding is
 * still missing (provider out of credits, outage, or a spent allowance).
 *
 * It stays hidden while nothing is pending. The worker fills the vectors in on
 * its own; "Retry now" only shortens the wait after a recharge or a key fix.
 */
export function EmbeddingBackfillNotice() {
  const { t, formatNumber, formatDateTime } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const statusQuery = useGetEmbeddingBackfillStatus({
    query: { retry: false, staleTime: 30_000, refetchInterval: 60_000 },
  });
  const retryMutation = useRetryEmbeddingBackfill();
  const status = statusQuery.data;
  if (!status || !hasBackfillNews(status)) {
    return null;
  }

  const handleRetry = async () => {
    try {
      const next = await retryMutation.mutateAsync();
      retryMutation.reset();
      queryClient.setQueryData(getGetEmbeddingBackfillStatusQueryKey(), next);
      toast.success(t("core.notices.embeddings.retryRequested"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "core.notices.embeddings.retryError"));
    }
  };

  const paused = status.worker_state === "paused";
  return (
    <div className="system-notice system-notice--embeddings" role="status">
      <div className="system-notice__head">
        <div className="system-notice__heading">
          <p className="mono-label">{t("settings.providers.capabilityEmbedding")}</p>
          <p>
            {t("core.notices.embeddings.pending", {
              count: formatNumber(status.pending_chunks),
              accounts: formatNumber(status.pending_accounts),
            })}
          </p>
          <p className="system-notice__code">
            <Badge tone={paused ? "vermilion" : "neutral"} dot>
              {t(STATE_LABELS[stateKey(status.worker_state)])}
            </Badge>
            {status.last_error_code ? <code>{status.last_error_code}</code> : null}
            {paused && status.resume_at ? (
              <span>
                {t("core.notices.embeddings.resumeAt", {
                  time: formatDateTime(status.resume_at),
                })}
              </span>
            ) : null}
          </p>
          {status.allowance_blocked_accounts > 0 ? (
            <p className="system-notices__quiet">
              {t("core.notices.embeddings.allowanceBlocked", {
                count: formatNumber(status.allowance_blocked_accounts),
              })}
            </p>
          ) : null}
          {status.abandoned_chunks > 0 ? (
            <p className="system-notices__quiet">
              {t("core.notices.embeddings.abandoned", {
                count: formatNumber(status.abandoned_chunks),
              })}
            </p>
          ) : null}
        </div>
        <div className="system-notice__actions">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void handleRetry()}
            disabled={retryMutation.isPending || status.pending_chunks === 0}
          >
            <Icon name="ring" size={13} />
            {retryMutation.isPending
              ? t("core.common.retrying")
              : t("core.notices.embeddings.retry")}
          </Button>
        </div>
      </div>
    </div>
  );
}

type StateKey = "running" | "idle" | "paused" | "disabled" | "unknown";

const STATE_LABELS = {
  running: "core.notices.embeddings.state.running",
  idle: "core.notices.embeddings.state.idle",
  paused: "core.notices.embeddings.state.paused",
  disabled: "core.notices.embeddings.state.disabled",
  unknown: "core.notices.embeddings.state.unknown",
} as const satisfies Record<StateKey, string>;

function stateKey(value: string): StateKey {
  switch (value) {
    case "running":
    case "idle":
    case "paused":
    case "disabled":
      return value;
    default:
      return "unknown";
  }
}
