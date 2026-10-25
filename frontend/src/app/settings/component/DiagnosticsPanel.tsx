import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  useGetAiStatus,
  useGetHealth,
  useGetProviderRegistry,
  useGetStats,
  useReindexEmbeddings,
} from "../../generated-apis-types";
import type {
  AiStatusSchema,
  EmbeddingReindexSchema,
  HealthSchema,
  StatsSchema,
} from "../../generated-apis-types/schemas";
import { formatBytes } from "../../../lib/format";
import { localizeStatus, useI18n, type Translate } from "../../i18n";
import { invalidateReindexQueries } from "./settings-invalidation";
import {
  apiErrorMessage,
  serviceTone,
  systemTone,
  toneToBadge,
  type SettingsTone,
} from "./settings-utils";
import { StatusPill } from "./StatusPill";

function healthLabel(value: string | undefined, t: Translate): string {
  if (value === "ok") {
    return t("settings.diagnostics.statusOnline");
  }
  if (value === "degraded") {
    return t("settings.diagnostics.statusDegraded");
  }
  if (value === "error") {
    return t("settings.diagnostics.statusError");
  }
  return t("settings.diagnostics.statusUnknown");
}

function aiLabel(
  configured: boolean | null,
  isError: boolean,
  t: Translate,
): string {
  if (isError) {
    return t("settings.diagnostics.statusUnavailable");
  }
  if (configured === null) {
    return t("settings.diagnostics.statusReading");
  }
  return configured
    ? t("settings.diagnostics.statusConfigured")
    : t("settings.diagnostics.statusNoProvider");
}

function overallLabel(
  tone: SettingsTone,
  pending: boolean,
  t: Translate,
): string {
  if (pending) {
    return t("settings.diagnostics.overallReading");
  }
  switch (tone) {
    case "ok":
      return t("settings.diagnostics.overallOnline");
    case "degraded":
      return t("settings.diagnostics.overallDegraded");
    case "error":
      return t("settings.diagnostics.overallOffline");
    default:
      return t("settings.diagnostics.overallUnknown");
  }
}

function resolveAiConfigured(
  ai: AiStatusSchema | undefined,
  health: HealthSchema | undefined,
): boolean | null {
  if (ai) {
    return ai.configured;
  }
  if (health) {
    return health.ai === "configured";
  }
  return null;
}

function aiToneFor(configured: boolean | null, isError: boolean): SettingsTone {
  if (isError) {
    return "error";
  }
  if (configured === null) {
    return "unknown";
  }
  return configured ? "ok" : "degraded";
}

function vectorToneFor(enabled: boolean | undefined): SettingsTone {
  if (enabled === undefined) {
    return "unknown";
  }
  return enabled ? "ok" : "degraded";
}

function vectorStatusLabel(
  enabled: boolean | undefined,
  isError: boolean,
  t: Translate,
): string {
  if (enabled === undefined) {
    return isError
      ? t("settings.diagnostics.statusUnavailable")
      : t("settings.diagnostics.statusReading");
  }
  return enabled
    ? t("settings.diagnostics.statusEnabled")
    : t("settings.diagnostics.statusDisabled");
}

function webStatusLabel(
  configured: boolean | undefined,
  isError: boolean,
  t: Translate,
): string {
  if (isError) {
    return t("settings.diagnostics.statusUnavailable");
  }
  if (configured === undefined) {
    return t("settings.diagnostics.statusUnknown");
  }
  return configured
    ? t("settings.diagnostics.statusConfigured")
    : t("settings.diagnostics.statusNeedsKey");
}

function configuredValueLabel(
  configured: boolean | undefined,
  t: Translate,
): string {
  if (configured === undefined) {
    return "—";
  }
  return configured
    ? t("settings.diagnostics.statusYes")
    : t("settings.diagnostics.statusNo");
}

function dimensionLabel(
  dimension: number | null | undefined,
  t: Translate,
): string {
  if (dimension === null || dimension === undefined) {
    return t("settings.diagnostics.statusProviderDefault");
  }
  return t("settings.diagnostics.statusDimension", {
    dimension: String(dimension),
  });
}

function reindexStateLabel(
  required: boolean | undefined,
  t: Translate,
): string {
  if (required === undefined) {
    return "—";
  }
  return required
    ? t("settings.diagnostics.statusRequired")
    : t("settings.diagnostics.statusCurrent");
}

function statsNote(
  isPending: boolean,
  isError: boolean,
  t: Translate,
): string | undefined {
  if (isPending) {
    return t("settings.diagnostics.statsNoteReading");
  }
  if (isError) {
    return t("settings.diagnostics.statsNoteUnavailable");
  }
  return undefined;
}

function DiagnosticItem({
  title,
  tone,
  status,
  rows,
  loading,
  note,
}: {
  readonly title: string;
  readonly tone: SettingsTone;
  readonly status: string;
  readonly rows: ReadonlyArray<{ readonly key: string; readonly value: string }>;
  readonly loading: boolean;
  readonly note?: string;
}) {
  if (loading) {
    return (
      <article className="diag-item diag-item--loading" aria-hidden="true">
        <div className="diag-top">
          <span className="settings-skeleton settings-skeleton--line is-short" />
          <span className="settings-skeleton settings-skeleton--badge" />
        </div>
        <span className="settings-skeleton settings-skeleton--line" />
        <span className="settings-skeleton settings-skeleton--line is-short" />
      </article>
    );
  }

  return (
    <article className="diag-item">
      <div className="diag-top">
        <h3 className="diag-title">{title}</h3>
        <StatusPill tone={tone}>{status}</StatusPill>
      </div>
      <dl className="diag-rows">
        {rows.map((row) => (
          <div className="diag-row" key={row.key}>
            <dt>{row.key}</dt>
            <dd title={row.value}>{row.value}</dd>
          </div>
        ))}
      </dl>
      {note ? <p className="diag-note">{note}</p> : null}
    </article>
  );
}

function StatsGrid({
  stats,
  isPending,
  isError,
}: {
  readonly stats: StatsSchema | undefined;
  readonly isPending: boolean;
  readonly isError: boolean;
}) {
  const { t, formatNumber, formatDate } = useI18n();
  const note = statsNote(isPending, isError, t);

  return (
    <div
      className="diagnostics-stats"
      aria-label={t("settings.diagnostics.statsAria")}
      aria-busy={isPending}
    >
      <div className="diagnostics-stat">
        <span>{t("settings.diagnostics.statFiles")}</span>
        <strong>{stats ? formatNumber(stats.file_count) : "—"}</strong>
        {note ? <small>{note}</small> : null}
      </div>
      <div className="diagnostics-stat">
        <span>{t("settings.diagnostics.statChunks")}</span>
        <strong>{stats ? formatNumber(stats.chunk_count) : "—"}</strong>
        {note ? <small>{note}</small> : null}
      </div>
      <div className="diagnostics-stat">
        <span>{t("settings.diagnostics.statMemories")}</span>
        <strong>{stats ? formatNumber(stats.memory_count) : "—"}</strong>
        <small>
          {stats
            ? t("settings.diagnostics.statActive", {
                count: formatNumber(stats.active_memory_count),
              })
            : (note ?? "")}
        </small>
      </div>
      <div className="diagnostics-stat">
        <span>{t("settings.diagnostics.statSummaries")}</span>
        <strong>{stats ? formatNumber(stats.summary_count) : "—"}</strong>
        {note ? <small>{note}</small> : null}
      </div>
      <dl className="diagnostics-facts">
        <div>
          <dt>{t("settings.diagnostics.factStorage")}</dt>
          <dd>{stats ? formatBytes(stats.storage_bytes) : "—"}</dd>
        </div>
        <div>
          <dt>{t("settings.diagnostics.factOldestMemory")}</dt>
          <dd>
            {stats?.oldest_memory_time
              ? formatDate(stats.oldest_memory_time)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>{t("settings.diagnostics.factNewestMemory")}</dt>
          <dd>
            {stats?.newest_memory_time
              ? formatDate(stats.newest_memory_time)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>{t("settings.diagnostics.factSource")}</dt>
          <dd>GET /api/v1/stats</dd>
        </div>
      </dl>
    </div>
  );
}

function DiagnosticsError({
  healthError,
  aiError,
  statsError,
  registryError,
  refreshing,
  onRetry,
}: {
  readonly healthError: unknown;
  readonly aiError: unknown;
  readonly statsError: unknown;
  readonly registryError: unknown;
  readonly refreshing: boolean;
  readonly onRetry: () => void;
}) {
  const { t } = useI18n();
  const parts: string[] = [];
  if (healthError) {
    parts.push(
      t("settings.diagnostics.errorHealth", {
        message: apiErrorMessage(healthError),
      }),
    );
  }
  if (aiError) {
    parts.push(
      t("settings.diagnostics.errorAi", {
        message: apiErrorMessage(aiError),
      }),
    );
  }
  if (statsError) {
    parts.push(
      t("settings.diagnostics.errorStats", {
        message: apiErrorMessage(statsError),
      }),
    );
  }
  if (registryError) {
    parts.push(
      t("settings.diagnostics.errorRegistry", {
        message: apiErrorMessage(registryError),
      }),
    );
  }

  return (
    <div className="settings-inline-error" role="alert">
      <Icon name="info" size={16} />
      <div>
        <strong>{t("settings.diagnostics.errorTitle")}</strong>
        <p>{parts.join(" · ")}</p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onRetry}
          disabled={refreshing}
        >
          <Icon name="ring" size={14} />
          {refreshing ? t("core.common.retrying") : t("core.common.retry")}
        </Button>
      </div>
    </div>
  );
}

function ReindexSection({
  vectorEnabled,
  chunkCount,
  statsPending,
  statsError,
  embeddingModel,
}: {
  readonly vectorEnabled: boolean | undefined;
  readonly chunkCount: number | undefined;
  readonly statsPending: boolean;
  readonly statsError: boolean;
  readonly embeddingModel: string;
}) {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<EmbeddingReindexSchema | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reindex = useReindexEmbeddings({
    mutation: {
      onSuccess: async (data) => {
        setResult(data);
        setError(null);
        setConfirming(false);
        toast.success(
          t("settings.reindex.toast", {
            count: formatNumber(data.reindexed),
            model: data.model,
          }),
        );
        await invalidateReindexQueries(queryClient);
      },
      onError: (mutationError) => {
        const message = apiErrorMessage(mutationError);
        setError(message);
        setConfirming(false);
        toast.error(message);
      },
    },
  });

  const canReindex =
    vectorEnabled === true &&
    chunkCount !== undefined &&
    chunkCount > 0 &&
    !reindex.isPending;

  let hint = t("settings.diagnostics.reindexHints.enable");
  if (vectorEnabled === true && statsPending) {
    hint = t("settings.diagnostics.reindexHints.reading");
  } else if (vectorEnabled === true && statsError) {
    hint = t("settings.diagnostics.reindexHints.error");
  } else if (vectorEnabled === true && chunkCount === 0) {
    hint = t("settings.diagnostics.reindexHints.noChunks");
  } else if (vectorEnabled === true) {
    hint = t("settings.diagnostics.reindexHints.running");
  }

  return (
    <>
      <div className="reindex">
        <div className="reindex__copy">
          <p className="mono-label">{t("settings.reindex.eyebrow")}</p>
          <h3 className="reindex__title">{t("settings.reindex.title")}</h3>
          <p className="reindex__text">
            {t("settings.reindex.textBefore")}
            <code>{embeddingModel}</code>
            {t("settings.reindex.textAfter")}
          </p>
          <p className="reindex__hint">{hint}</p>
        </div>
        <div className="reindex__action">
          {confirming ? (
            <div className="reindex__confirm" role="status">
              <span>
                {t("settings.diagnostics.reindexConfirm", {
                  count: formatNumber(chunkCount ?? 0),
                  model: embeddingModel,
                })}
              </span>
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={() => reindex.mutate()}
                disabled={reindex.isPending}
              >
                {reindex.isPending
                  ? t("settings.reindex.reembedding")
                  : t("settings.reindex.start")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(false)}
                disabled={reindex.isPending}
              >
                {t("settings.common.cancel")}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="ink"
              size="sm"
              onClick={() => {
                setError(null);
                setConfirming(true);
              }}
              disabled={!canReindex}
            >
              <Icon name="history" size={14} />
              {reindex.isPending
                ? t("settings.reindex.reembedding")
                : t("settings.reindex.action")}
            </Button>
          )}
        </div>
      </div>

      {result ? (
        <p className="reindex__result" role="status">
          <Icon name="check" size={14} />
          {t("settings.reindex.result", {
            count: formatNumber(result.reindexed),
            model: result.model,
            dimension: String(result.dimension),
            ms: formatNumber(result.elapsed_ms),
          })}
        </p>
      ) : null}

      {error ? (
        <p className="vault-feedback vault-feedback--error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}
    </>
  );
}

/** Live health, AI configuration, archive counts, and vector maintenance. */
export function DiagnosticsPanel() {
  const { t } = useI18n();
  const healthQuery = useGetHealth({ query: { staleTime: 30_000 } });
  const aiQuery = useGetAiStatus({ query: { staleTime: 60_000 } });
  const statsQuery = useGetStats({ query: { staleTime: 30_000 } });
  const registryQuery = useGetProviderRegistry({
    query: { staleTime: 30_000 },
  });

  const health = healthQuery.data;
  const ai = aiQuery.data;
  const stats = statsQuery.data;
  const registry = registryQuery.data;
  const embeddingGroup = registry?.capabilities.find(
    (group) => group.capability === "embedding",
  );
  const embeddingActive = embeddingGroup?.active;

  const anyError =
    healthQuery.isError ||
    aiQuery.isError ||
    statsQuery.isError ||
    registryQuery.isError;
  const anyPending =
    healthQuery.isPending ||
    aiQuery.isPending ||
    statsQuery.isPending ||
    registryQuery.isPending;
  const refreshing =
    healthQuery.isFetching ||
    aiQuery.isFetching ||
    statsQuery.isFetching ||
    registryQuery.isFetching;

  let overallTone = systemTone(
    health,
    healthQuery.isError,
    healthQuery.isPending,
  );
  if (
    !healthQuery.isError &&
    (aiQuery.isError || statsQuery.isError || registryQuery.isError)
  ) {
    overallTone = "degraded";
  }
  const aiConfigured = resolveAiConfigured(ai, health);
  const aiTone = aiToneFor(aiConfigured, aiQuery.isError);
  const vectorEnabled = registry?.vector_enabled ?? ai?.vector_enabled;
  const vectorTone = vectorToneFor(vectorEnabled);
  const embeddingProvider =
    ai?.embedding_provider ??
    embeddingActive?.provider ??
    health?.embedding_provider ??
    "—";
  const embeddingModel = ai?.embedding_model ?? embeddingActive?.model ?? "—";
  const reindexRequired = registry?.reindex_required;

  const retryDiagnostics = () => {
    void Promise.all([
      healthQuery.refetch(),
      aiQuery.refetch(),
      statsQuery.refetch(),
      registryQuery.refetch(),
    ]);
  };

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="overview" size={16} />
          {t("settings.diagnostics.title")}
        </span>
      }
      action={
        <div className="settings-panel__badges">
          <Badge tone={toneToBadge(overallTone)} dot>
            {overallLabel(overallTone, anyPending, t)}
          </Badge>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={retryDiagnostics}
            disabled={refreshing}
          >
            <Icon name="ring" size={13} />
            {refreshing
              ? t("settings.diagnostics.refreshing")
              : t("settings.diagnostics.refresh")}
          </Button>
        </div>
      }
      className="settings-panel"
    >
      <p className="settings-lede">{t("settings.diagnostics.lede")}</p>

      {anyError ? (
        <DiagnosticsError
          healthError={healthQuery.isError ? healthQuery.error : null}
          aiError={aiQuery.isError ? aiQuery.error : null}
          statsError={statsQuery.isError ? statsQuery.error : null}
          registryError={
            registryQuery.isError ? registryQuery.error : null
          }
          refreshing={refreshing}
          onRetry={retryDiagnostics}
        />
      ) : null}

      <div className="diagnostics-grid" aria-busy={anyPending}>
        <DiagnosticItem
          title={t("settings.diagnostics.itemDatabase")}
          tone={serviceTone(health?.database)}
          status={
            healthQuery.isError
              ? t("settings.diagnostics.statusUnavailable")
              : healthLabel(health?.database, t)
          }
          rows={[
            {
              key: t("settings.diagnostics.rowApiStatus"),
              value: health?.status
                ? localizeStatus(t, health.status)
                : "—",
            },
            {
              key: t("settings.diagnostics.rowVersion"),
              value: health?.version ?? "—",
            },
            {
              key: t("settings.diagnostics.rowDatabase"),
              value: health?.database
                ? localizeStatus(t, health.database)
                : "—",
            },
          ]}
          loading={healthQuery.isPending}
        />
        <DiagnosticItem
          title={t("settings.diagnostics.itemCache")}
          tone={serviceTone(health?.cache)}
          status={
            healthQuery.isError
              ? t("settings.diagnostics.statusUnavailable")
              : healthLabel(health?.cache, t)
          }
          rows={[
            {
              key: t("settings.diagnostics.rowReportedStatus"),
              value: health?.cache ? localizeStatus(t, health.cache) : "—",
            },
            {
              key: t("settings.diagnostics.rowFallback"),
              value: t("settings.diagnostics.valueInProcessCache"),
            },
            {
              key: t("settings.diagnostics.rowEffect"),
              value:
                health?.cache === "ok"
                  ? t("settings.diagnostics.valueCacheReachable")
                  : t("settings.diagnostics.valueReadsStillWork"),
            },
          ]}
          loading={healthQuery.isPending}
          note={t("settings.diagnostics.cacheNote")}
        />
        <DiagnosticItem
          title={t("settings.diagnostics.itemAi")}
          tone={aiTone}
          status={aiLabel(aiConfigured, aiQuery.isError, t)}
          rows={[
            {
              key: t("settings.diagnostics.rowProvider"),
              value: ai?.provider ?? "—",
            },
            {
              key: t("settings.diagnostics.rowModel"),
              value: ai?.model ?? "—",
            },
            {
              key: t("settings.diagnostics.rowHealth"),
              value: health?.ai ? localizeStatus(t, health.ai) : "—",
            },
          ]}
          loading={aiQuery.isPending}
        />
        <DiagnosticItem
          title={t("settings.diagnostics.itemVector")}
          tone={vectorTone}
          status={vectorStatusLabel(
            vectorEnabled,
            aiQuery.isError || registryQuery.isError,
            t,
          )}
          rows={[
            {
              key: t("settings.diagnostics.rowEmbeddingProvider"),
              value: embeddingProvider,
            },
            {
              key: t("settings.diagnostics.rowEmbeddingModel"),
              value: embeddingModel,
            },
            {
              key: t("settings.diagnostics.rowDimension"),
              value: dimensionLabel(
                embeddingActive?.dimension,
                t,
              ),
            },
            {
              key: t("settings.diagnostics.rowReindex"),
              value: reindexStateLabel(reindexRequired, t),
            },
          ]}
          loading={registryQuery.isPending}
        />
        <DiagnosticItem
          title={t("settings.diagnostics.itemWebSearch")}
          tone={aiToneFor(ai?.web_search_configured ?? null, aiQuery.isError)}
          status={webStatusLabel(
            ai?.web_search_configured,
            aiQuery.isError,
            t,
          )}
          rows={[
            {
              key: t("settings.diagnostics.rowProvider"),
              value: ai?.web_search_provider ?? "—",
            },
            {
              key: t("settings.diagnostics.rowConfigured"),
              value: configuredValueLabel(ai?.web_search_configured, t),
            },
            {
              key: t("settings.diagnostics.rowCredential"),
              value: t("settings.diagnostics.valueSeparateWebSearch"),
            },
          ]}
          loading={aiQuery.isPending}
        />
        <DiagnosticItem
          title={t("settings.diagnostics.itemWebFetch")}
          tone={aiToneFor(ai?.web_fetch_configured ?? null, aiQuery.isError)}
          status={webStatusLabel(ai?.web_fetch_configured, aiQuery.isError, t)}
          rows={[
            {
              key: t("settings.diagnostics.rowProvider"),
              value: ai?.web_fetch_provider ?? "—",
            },
            {
              key: t("settings.diagnostics.rowConfigured"),
              value: configuredValueLabel(ai?.web_fetch_configured, t),
            },
            {
              key: t("settings.diagnostics.rowCredential"),
              value: t("settings.diagnostics.valueSeparateWebFetch"),
            },
          ]}
          loading={aiQuery.isPending}
        />
      </div>

      <div className="diagnostics-section">
        <div className="diagnostics-section__head">
          <p className="mono-label">
            {t("settings.diagnostics.statsSectionLabel")}
          </p>
          <span className="diagnostics-section__source">
            GET /api/v1/stats
          </span>
        </div>
        <StatsGrid
          stats={stats}
          isPending={statsQuery.isPending}
          isError={statsQuery.isError}
        />
      </div>

      <ReindexSection
        vectorEnabled={vectorEnabled}
        chunkCount={stats?.chunk_count}
        statsPending={statsQuery.isPending}
        statsError={statsQuery.isError}
        embeddingModel={embeddingModel}
      />
    </Panel>
  );
}
