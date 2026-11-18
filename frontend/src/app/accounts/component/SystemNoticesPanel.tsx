import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  getListProviderNoticesQueryKey,
  useListProviderNotices,
  useResolveAllProviderNotices,
  useResolveProviderNotice,
} from "../../generated-apis-types";
import type {
  ProviderErrorNoticeReadSchema,
  ProviderErrorNoticeListSchema,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n, type Translate } from "../../i18n";

function capabilityLabel(
  capability: ProviderErrorNoticeReadSchema["capability"],
  t: Translate,
): string {
  switch (capability) {
    case "chat":
      return t("settings.providers.capabilityChat");
    case "embedding":
      return t("settings.providers.capabilityEmbedding");
    case "web_search":
      return t("settings.providers.capabilityWebSearch");
    case "web_fetch":
      return t("settings.providers.capabilityWebFetch");
  }
}

function NoticeRow({
  notice,
  busy,
  onResolve,
}: {
  readonly notice: ProviderErrorNoticeReadSchema;
  readonly busy: boolean;
  readonly onResolve: (notice: ProviderErrorNoticeReadSchema) => void;
}) {
  const { t, formatDateTime, formatNumber } = useI18n();
  return (
    <li className="system-notice">
      <div className="system-notice__head">
        <div className="system-notice__heading">
          <p className="mono-label">
            {capabilityLabel(notice.capability, t)} ·{" "}
            <code>{notice.operation}</code>
          </p>
          <p className="system-notice__code">
            <code>{notice.error_code}</code>
            {notice.status_code !== null ? (
              <>
                <span aria-hidden="true">·</span>
                <code>HTTP {notice.status_code}</code>
              </>
            ) : null}
            <span aria-hidden="true">·</span>
            <Badge tone="vermilion">
              {t("core.notices.count", {
                count: formatNumber(notice.count),
              })}
            </Badge>
          </p>
        </div>
        <div className="system-notice__actions">
          <time dateTime={notice.last_seen_at}>
            {t("core.notices.lastSeen", {
              time: formatDateTime(notice.last_seen_at),
            })}
          </time>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onResolve(notice)}
            disabled={busy}
          >
            <Icon name="check" size={13} />
            {busy ? t("core.notices.resolving") : t("core.notices.resolve")}
          </Button>
        </div>
      </div>
      <p className="system-notice__detail">{notice.detail}</p>
      {notice.attempts.length > 0 ? (
        <ol className="system-notice__attempts">
          {notice.attempts.map((attempt, index) => (
            <li
              className="system-notice__attempt"
              key={`${attempt.provider}-${index}`}
            >
              <span className="system-notice__attempt-provider">
                {attempt.provider}
              </span>
              {attempt.status_code !== null ? (
                <code>HTTP {attempt.status_code}</code>
              ) : null}
              {attempt.error_code ? <code>{attempt.error_code}</code> : null}
              {attempt.detail ? (
                <span className="system-notice__attempt-detail">
                  {attempt.detail}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}
    </li>
  );
}

/**
 * Root-only operational notices for whole provider-chain failures.
 *
 * The panel is intentionally quiet while the system is healthy: an empty line
 * is not an error state. Resolution invalidates the list so every root tab
 * reflects the new count.
 */
export function SystemNoticesPanel() {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const noticesQuery = useListProviderNotices(undefined, {
    query: { retry: false, staleTime: 30_000 },
  });
  const resolveMutation = useResolveProviderNotice();
  const resolveAllMutation = useResolveAllProviderNotices();

  const invalidateNotices = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: getListProviderNoticesQueryKey(),
    });
  };

  const applyResolvedList = (
    listing: ProviderErrorNoticeListSchema,
  ): void => {
    queryClient.setQueryData(getListProviderNoticesQueryKey(), listing);
  };

  const handleResolve = async (notice: ProviderErrorNoticeReadSchema) => {
    try {
      await resolveMutation.mutateAsync({ noticeId: notice.id });
      resolveMutation.reset();
      await invalidateNotices();
      toast.success(t("core.notices.resolveSuccess"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "core.notices.resolveError"));
    }
  };

  const handleResolveAll = async () => {
    try {
      const listing = await resolveAllMutation.mutateAsync();
      resolveAllMutation.reset();
      applyResolvedList(listing);
      await invalidateNotices();
      toast.success(t("core.notices.resolveAllSuccess"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "core.notices.resolveError"));
    }
  };

  const listing = noticesQuery.data;
  const openCount = listing?.open_count ?? 0;
  const busy = resolveMutation.isPending || resolveAllMutation.isPending;
  let body;
  if (noticesQuery.isPending) {
    body = (
      <p className="system-notices__quiet" role="status">
        {t("core.notices.loading")}
      </p>
    );
  } else if (noticesQuery.isError) {
    body = (
      <div className="system-notices__error" role="alert">
        <Icon name="info" size={15} />
        <div>
          <p>{apiErrorMessage(noticesQuery.error, "core.notices.loadError")}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void noticesQuery.refetch()}
            disabled={noticesQuery.isFetching}
          >
            <Icon name="ring" size={14} />
            {noticesQuery.isFetching
              ? t("core.common.retrying")
              : t("core.common.retry")}
          </Button>
        </div>
      </div>
    );
  } else if (!listing || listing.notices.length === 0) {
    body = (
      <p className="system-notices__quiet">
        {t("core.notices.empty")}
      </p>
    );
  } else {
    body = (
      <ul className="system-notices__list">
        {listing.notices.map((notice) => (
          <NoticeRow
            key={notice.id}
            notice={notice}
            busy={busy}
            onResolve={(target) => void handleResolve(target)}
          />
        ))}
      </ul>
    );
  }

  return (
    <Panel
      tone="plain"
      className="system-notices"
      title={t("core.notices.title")}
      action={
        <div className="system-notices__toolbar">
          <Badge tone={openCount > 0 ? "vermilion" : "neutral"} dot>
            {t("core.notices.openCount", {
              count: formatNumber(openCount),
            })}
          </Badge>
          {openCount > 0 ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void handleResolveAll()}
              disabled={busy}
            >
              <Icon name="check" size={13} />
              {resolveAllMutation.isPending
                ? t("core.notices.resolving")
                : t("core.notices.resolveAll")}
            </Button>
          ) : null}
        </div>
      }
    >
      {body}
    </Panel>
  );
}
