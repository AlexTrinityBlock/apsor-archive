import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  useGetAiSettings,
  useGetAiStatus,
  useGetHealth,
  useGetStats,
  useReindexEmbeddings,
} from "../../generated-apis-types";
import type {
  AiStatusSchema,
  EmbeddingReindexSchema,
  HealthSchema,
  StatsSchema,
} from "../../generated-apis-types/schemas";
import { formatBytes, formatDate, formatNumber } from "../../../lib/format";
import { invalidateReindexQueries } from "./settings-invalidation";
import {
  apiErrorMessage,
  serviceTone,
  systemTone,
  toneToBadge,
  type SettingsTone,
} from "./settings-utils";
import { StatusPill } from "./StatusPill";

function healthLabel(value: string | undefined): string {
  if (value === "ok") {
    return "Online";
  }
  if (value === "degraded") {
    return "Degraded";
  }
  if (value === "error") {
    return "Error";
  }
  return "Unknown";
}

function aiLabel(configured: boolean | null, isError: boolean): string {
  if (isError) {
    return "Unavailable";
  }
  if (configured === null) {
    return "Reading";
  }
  return configured ? "Configured" : "No provider";
}

function overallLabel(tone: SettingsTone, pending: boolean): string {
  if (pending) {
    return "Reading";
  }
  switch (tone) {
    case "ok":
      return "All systems online";
    case "degraded":
      return "Degraded";
    case "error":
      return "Offline";
    default:
      return "Unknown";
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
): string {
  if (enabled === undefined) {
    return isError ? "Unavailable" : "Reading";
  }
  return enabled ? "Enabled" : "Disabled";
}

function dimensionLabel(dimension: number | null | undefined): string {
  if (dimension === null || dimension === undefined) {
    return "Provider default";
  }
  return `${formatNumber(dimension)}-D`;
}

function reindexStateLabel(required: boolean | undefined): string {
  if (required === undefined) {
    return "—";
  }
  return required ? "Required" : "Current";
}

function statsNote(
  isPending: boolean,
  isError: boolean,
): string | undefined {
  if (isPending) {
    return "reading";
  }
  if (isError) {
    return "unavailable";
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
  const note = statsNote(isPending, isError);

  return (
    <div
      className="diagnostics-stats"
      aria-label="Archive counts"
      aria-busy={isPending}
    >
      <div className="diagnostics-stat">
        <span>Files archived</span>
        <strong>{stats ? formatNumber(stats.file_count) : "—"}</strong>
        {note ? <small>{note}</small> : null}
      </div>
      <div className="diagnostics-stat">
        <span>Indexed chunks</span>
        <strong>{stats ? formatNumber(stats.chunk_count) : "—"}</strong>
        {note ? <small>{note}</small> : null}
      </div>
      <div className="diagnostics-stat">
        <span>Memory crystals</span>
        <strong>{stats ? formatNumber(stats.memory_count) : "—"}</strong>
        <small>
          {stats
            ? `${formatNumber(stats.active_memory_count)} active`
            : (note ?? "")}
        </small>
      </div>
      <div className="diagnostics-stat">
        <span>AI summaries</span>
        <strong>{stats ? formatNumber(stats.summary_count) : "—"}</strong>
        {note ? <small>{note}</small> : null}
      </div>
      <dl className="diagnostics-facts">
        <div>
          <dt>Storage</dt>
          <dd>{stats ? formatBytes(stats.storage_bytes) : "—"}</dd>
        </div>
        <div>
          <dt>Oldest memory</dt>
          <dd>
            {stats?.oldest_memory_time
              ? formatDate(stats.oldest_memory_time)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Newest memory</dt>
          <dd>
            {stats?.newest_memory_time
              ? formatDate(stats.newest_memory_time)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Source</dt>
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
  settingsError,
  refreshing,
  onRetry,
}: {
  readonly healthError: unknown;
  readonly aiError: unknown;
  readonly statsError: unknown;
  readonly settingsError: unknown;
  readonly refreshing: boolean;
  readonly onRetry: () => void;
}) {
  const parts: string[] = [];
  if (healthError) {
    parts.push(`Health: ${apiErrorMessage(healthError)}`);
  }
  if (aiError) {
    parts.push(`AI status: ${apiErrorMessage(aiError)}`);
  }
  if (statsError) {
    parts.push(`Stats: ${apiErrorMessage(statsError)}`);
  }
  if (settingsError) {
    parts.push(`Provider settings: ${apiErrorMessage(settingsError)}`);
  }

  return (
    <div className="settings-inline-error" role="alert">
      <Icon name="info" size={16} />
      <div>
        <strong>Part of the diagnostic surface did not answer.</strong>
        <p>{parts.join(" · ")}</p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onRetry}
          disabled={refreshing}
        >
          <Icon name="ring" size={14} />
          {refreshing ? "Retrying…" : "Retry"}
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
          `Re-embedded ${formatNumber(data.reindexed)} chunks with ${data.model}.`,
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

  let hint = "Enable an embedding provider in the vault first.";
  if (vectorEnabled === true && statsPending) {
    hint = "Reading the current chunk count…";
  } else if (vectorEnabled === true && statsError) {
    hint = "The chunk count could not be read.";
  } else if (vectorEnabled === true && chunkCount === 0) {
    hint = "There are no current chunks to re-embed.";
  } else if (vectorEnabled === true) {
    hint =
      "Re-embedding runs synchronously against every current chunk and may take a while.";
  }

  return (
    <>
      <div className="reindex">
        <div className="reindex__copy">
          <p className="mono-label">Vector maintenance</p>
          <h3 className="reindex__title">Re-embed the library</h3>
          <p className="reindex__text">
            Recompute every current chunk with <code>{embeddingModel}</code> and
            replace the stored vectors. Use this after changing the embedding
            model or dimension.
          </p>
          <p className="reindex__hint">{hint}</p>
        </div>
        <div className="reindex__action">
          {confirming ? (
            <div className="reindex__confirm" role="status">
              <span>
                Re-embed {formatNumber(chunkCount ?? 0)} current chunks with{" "}
                {embeddingModel}? This may take a while.
              </span>
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={() => reindex.mutate()}
                disabled={reindex.isPending}
              >
                {reindex.isPending ? "Re-embedding…" : "Start re-index"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(false)}
                disabled={reindex.isPending}
              >
                Cancel
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
              {reindex.isPending ? "Re-embedding…" : "Re-index embeddings"}
            </Button>
          )}
        </div>
      </div>

      {result ? (
        <p className="reindex__result" role="status">
          <Icon name="check" size={14} />
          Re-embedded {formatNumber(result.reindexed)} chunks with{" "}
          <code>{result.model}</code> · {formatNumber(result.dimension)}-D ·{" "}
          {formatNumber(result.elapsed_ms)} ms.
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
  const healthQuery = useGetHealth({ query: { staleTime: 30_000 } });
  const aiQuery = useGetAiStatus({ query: { staleTime: 60_000 } });
  const statsQuery = useGetStats({ query: { staleTime: 30_000 } });
  const aiSettingsQuery = useGetAiSettings({ query: { staleTime: 30_000 } });

  const health = healthQuery.data;
  const ai = aiQuery.data;
  const stats = statsQuery.data;
  const aiSettings = aiSettingsQuery.data;

  const anyError =
    healthQuery.isError ||
    aiQuery.isError ||
    statsQuery.isError ||
    aiSettingsQuery.isError;
  const anyPending =
    healthQuery.isPending ||
    aiQuery.isPending ||
    statsQuery.isPending ||
    aiSettingsQuery.isPending;
  const refreshing =
    healthQuery.isFetching ||
    aiQuery.isFetching ||
    statsQuery.isFetching ||
    aiSettingsQuery.isFetching;

  let overallTone = systemTone(
    health,
    healthQuery.isError,
    healthQuery.isPending,
  );
  if (
    !healthQuery.isError &&
    (aiQuery.isError || statsQuery.isError || aiSettingsQuery.isError)
  ) {
    overallTone = "degraded";
  }
  const aiConfigured = resolveAiConfigured(ai, health);
  const aiTone = aiToneFor(aiConfigured, aiQuery.isError);
  const vectorEnabled = aiSettings?.vector_enabled ?? ai?.vector_enabled;
  const vectorTone = vectorToneFor(vectorEnabled);
  const embeddingProvider =
    ai?.embedding_provider ??
    aiSettings?.embedding.provider ??
    health?.embedding_provider ??
    "—";
  const embeddingModel =
    ai?.embedding_model ?? aiSettings?.embedding.model ?? "—";
  const reindexRequired = aiSettings?.reindex_required;

  const retryDiagnostics = () => {
    void Promise.all([
      healthQuery.refetch(),
      aiQuery.refetch(),
      statsQuery.refetch(),
      aiSettingsQuery.refetch(),
    ]);
  };

  return (
    <Panel
      id="settings-diagnostics"
      title={
        <span className="settings-panel__title">
          <Icon name="overview" size={16} />
          System diagnostics
        </span>
      }
      action={
        <div className="settings-panel__badges">
          <Badge tone={toneToBadge(overallTone)} dot>
            {overallLabel(overallTone, anyPending)}
          </Badge>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={retryDiagnostics}
            disabled={refreshing}
          >
            <Icon name="ring" size={13} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      }
      className="settings-panel"
    >
      <p className="settings-lede">
        The API answers these checks from the live process. Only reported fields
        are shown: no synthetic latency, pool, or hit-ratio numbers.
      </p>

      {anyError ? (
        <DiagnosticsError
          healthError={healthQuery.isError ? healthQuery.error : null}
          aiError={aiQuery.isError ? aiQuery.error : null}
          statsError={statsQuery.isError ? statsQuery.error : null}
          settingsError={
            aiSettingsQuery.isError ? aiSettingsQuery.error : null
          }
          refreshing={refreshing}
          onRetry={retryDiagnostics}
        />
      ) : null}

      <div className="diagnostics-grid" aria-busy={anyPending}>
        <DiagnosticItem
          title="PostgreSQL database"
          tone={serviceTone(health?.database)}
          status={
            healthQuery.isError ? "Unavailable" : healthLabel(health?.database)
          }
          rows={[
            { key: "API status", value: health?.status ?? "—" },
            { key: "Version", value: health?.version ?? "—" },
            { key: "Database", value: health?.database ?? "—" },
          ]}
          loading={healthQuery.isPending}
        />
        <DiagnosticItem
          title="Cache"
          tone={serviceTone(health?.cache)}
          status={
            healthQuery.isError ? "Unavailable" : healthLabel(health?.cache)
          }
          rows={[
            { key: "Reported status", value: health?.cache ?? "—" },
            { key: "Fallback", value: "In-process cache" },
            {
              key: "Effect",
              value:
                health?.cache === "ok"
                  ? "Cache reachable"
                  : "Reads still work",
            },
          ]}
          loading={healthQuery.isPending}
          note="The health endpoint reports reachability; it does not expose ports or hit ratios."
        />
        <DiagnosticItem
          title="AI inference"
          tone={aiTone}
          status={aiLabel(aiConfigured, aiQuery.isError)}
          rows={[
            { key: "Provider", value: ai?.provider ?? "—" },
            { key: "Model", value: ai?.model ?? "—" },
            { key: "Health", value: health?.ai ?? "—" },
          ]}
          loading={aiQuery.isPending}
        />
        <DiagnosticItem
          title="Vector retrieval"
          tone={vectorTone}
          status={vectorStatusLabel(
            vectorEnabled,
            aiQuery.isError || aiSettingsQuery.isError,
          )}
          rows={[
            { key: "Embedding provider", value: embeddingProvider },
            { key: "Embedding model", value: embeddingModel },
            {
              key: "Dimension",
              value: dimensionLabel(aiSettings?.embedding.dimension),
            },
            { key: "Re-index", value: reindexStateLabel(reindexRequired) },
          ]}
          loading={aiSettingsQuery.isPending}
        />
      </div>

      <div className="diagnostics-section">
        <div className="diagnostics-section__head">
          <p className="mono-label">Archive volume</p>
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
