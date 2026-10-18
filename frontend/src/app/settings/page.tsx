import { useId, useState, type FormEvent, type ReactNode } from "react";
import {
  useIsFetching,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { ApiError } from "../../apis/fetch-client";
import { Badge } from "../component/Badge";
import { Button, ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useToast } from "../component/Toast";
import {
  getGetAiSettingsQueryKey,
  getGetAiStatusQueryKey,
  getGetHealthQueryKey,
  getGetStatsQueryKey,
  useClearAiProviderKey,
  useGetAiSettings,
  useGetAiStatus,
  useGetHealth,
  useGetStats,
  useReindexEmbeddings,
  useSeedDemo,
  useTestAiProvider,
  useUpdateAiProvider,
} from "../generated-apis-types";
import type {
  AiProviderReadSchema,
  AiProviderUpdateSchema,
  AiTestResultSchema,
  HealthSchema,
} from "../generated-apis-types/schemas";
import { useTheme } from "../hook/useTheme";
import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatNumber,
} from "../../lib/format";
import type { BadgeTone, ThemePreference } from "../type/ui";
import "./settings.css";

const THEME_OPTIONS: ReadonlyArray<{
  value: ThemePreference;
  label: string;
  description: string;
  swatches: readonly string[];
}> = [
  {
    value: "light",
    label: "Paper archive",
    description: "Warm paper, ink green, daylight reading.",
    swatches: ["#f3edde", "#17251c", "#b7462c"],
  },
  {
    value: "dark",
    label: "Night archive",
    description: "Low light, moss on near-black, quiet contrast.",
    swatches: ["#10160f", "#dfdfc9", "#93a879"],
  },
  {
    value: "system",
    label: "Follow system",
    description: "Use whichever palette the operating system prefers.",
    swatches: ["#f3edde", "#10160f", "#b9892f"],
  },
];

interface ProviderOption {
  readonly value: string;
  readonly label: string;
}

const CHAT_PROVIDER_OPTIONS: readonly ProviderOption[] = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "openai-compatible", label: "OpenAI-compatible" },
  { value: "none", label: "None (disabled)" },
];

const EMBEDDING_PROVIDER_OPTIONS: readonly ProviderOption[] = [
  { value: "hashing", label: "Hashing (offline)" },
  { value: "openai", label: "OpenAI" },
  { value: "openai-compatible", label: "OpenAI-compatible" },
  { value: "none", label: "None (disabled)" },
];

type SettingsTone = "ok" | "degraded" | "error" | "unknown";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The archive could not complete that action.";
}

function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail.trim().length > 0 ? error.detail : error.message;
  }
  return errorMessage(error);
}

async function invalidateProviderQueries(queryClient: QueryClient): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: getGetAiSettingsQueryKey(),
      refetchType: "none",
    }),
    queryClient.invalidateQueries({
      queryKey: getGetAiStatusQueryKey(),
      refetchType: "none",
    }),
    queryClient.invalidateQueries({
      queryKey: getGetHealthQueryKey(),
      refetchType: "none",
    }),
    queryClient.invalidateQueries({
      queryKey: getGetStatsQueryKey(),
      refetchType: "none",
    }),
  ]);
  await queryClient.invalidateQueries();
}

function serviceTone(value: string | undefined): SettingsTone {
  if (!value) {
    return "unknown";
  }
  if (value === "ok" || value === "configured") {
    return "ok";
  }
  if (value === "degraded" || value === "missing") {
    return "degraded";
  }
  return "error";
}

function systemTone(
  health: HealthSchema | undefined,
  isError: boolean,
  isPending: boolean,
): SettingsTone {
  if (isError) {
    return "error";
  }
  if (isPending || !health) {
    return "unknown";
  }
  if (health.status !== "ok" || health.database !== "ok") {
    return "error";
  }
  return health.cache === "ok" ? "ok" : "degraded";
}

function configuredTone(configured: boolean | null): SettingsTone {
  if (configured === null) {
    return "unknown";
  }
  return configured ? "ok" : "degraded";
}

function toneToBadge(tone: SettingsTone): BadgeTone {
  if (tone === "ok") {
    return "moss";
  }
  if (tone === "degraded") {
    return "ochre";
  }
  if (tone === "error") {
    return "vermilion";
  }
  return "neutral";
}

function systemBadgeLabel(tone: SettingsTone): string {
  switch (tone) {
    case "ok":
      return "Online";
    case "degraded":
      return "Degraded";
    case "error":
      return "Offline";
    default:
      return "Reading";
  }
}

function configuredBadgeLabel(configured: boolean | null): string {
  if (configured === null) {
    return "Reading";
  }
  return configured ? "Configured" : "Missing key";
}

function statsBadgeTone(hasData: boolean, isError: boolean): BadgeTone {
  if (hasData) {
    return "moss";
  }
  return isError ? "vermilion" : "neutral";
}

function statsBadgeLabel(hasData: boolean, isError: boolean): string {
  if (hasData) {
    return "Live";
  }
  return isError ? "Unavailable" : "Reading";
}

function configuredLabel(configured: boolean | null): string {
  if (configured === null) {
    return "—";
  }
  return configured ? "Yes" : "No";
}

function vectorLabel(enabled: boolean | undefined): string {
  if (enabled === undefined) {
    return "—";
  }
  return enabled ? "Enabled" : "Disabled";
}

function vectorStatusLabel(enabled: boolean | undefined): string {
  if (enabled === undefined) {
    return "Reading vector";
  }
  return enabled ? "Vector on" : "Vector off";
}

function SettingsDot({ tone }: { readonly tone: SettingsTone }) {
  return (
    <span
      className={`settings-status-dot settings-status-dot--${tone}`}
      aria-hidden="true"
    />
  );
}

function aiHealthLabel(value: string | undefined): string {
  if (value === "configured") {
    return "configured";
  }
  if (value === "missing") {
    return "missing";
  }
  return "—";
}

function apiStatusLabel(health: HealthSchema | undefined, isError: boolean): string {
  if (isError) {
    return "offline";
  }
  return health?.status ?? "—";
}

function aiStateLabel(
  configured: boolean | null,
  provider: string | undefined,
  model: string | undefined,
): string {
  if (configured === null) {
    return "Reading the AI configuration";
  }
  if (!configured) {
    return "No chat provider is configured";
  }
  return `${provider ?? "provider"} · ${model ?? "model not reported"}`;
}

function aiDetailLabel(configured: boolean | null): string {
  if (configured === null) {
    return "The archive is checking GET /api/v1/ai/status.";
  }
  if (!configured) {
    return "Ask stays blocked and summaries fall back to the extractive generator until a chat provider is configured.";
  }
  return "Summary and Ask calls use the configured provider. Only retrieved passages are sent.";
}

function sourceTone(source: AiProviderReadSchema["source"]): BadgeTone {
  if (source === "database") {
    return "moss";
  }
  if (source === "environment") {
    return "ochre";
  }
  return "neutral";
}

function providerStateLabel(config: AiProviderReadSchema): string {
  if (!config.enabled) {
    return "Disabled";
  }
  return config.configured ? "Configured" : "Needs attention";
}

function providerStateTone(config: AiProviderReadSchema): BadgeTone {
  if (!config.enabled) {
    return "neutral";
  }
  return config.configured ? "moss" : "ochre";
}

function providerKeyLabel(config: AiProviderReadSchema): string {
  if (config.provider === "none" || config.provider === "hashing") {
    return "no key required";
  }
  return config.key_hint ?? "no key stored";
}

function providerCardKey(config: AiProviderReadSchema): string {
  return [
    config.purpose,
    config.source,
    config.provider,
    config.model,
    config.enabled ? "enabled" : "disabled",
    config.key_hint ?? "no-key",
    config.updated_at ?? "new",
  ].join("|");
}

function providerFieldHint(purpose: AiProviderReadSchema["purpose"]): string {
  if (purpose === "chat") {
    return "DeepSeek uses its hosted endpoint. OpenAI-compatible requires a base URL.";
  }
  return "Hashing is offline. OpenAI-compatible requires a base URL.";
}

function modelFieldHint(purpose: AiProviderReadSchema["purpose"]): string {
  if (purpose === "chat") {
    return "Use deepseek-flash for DeepSeek.";
  }
  return "Recorded as the embedding model for new chunks.";
}

function baseUrlFieldHint(purpose: AiProviderReadSchema["purpose"]): string {
  if (purpose === "chat") {
    return "DeepSeek defaults to https://api.deepseek.com. Required for openai-compatible.";
  }
  return "Required for openai-compatible. Hashing ignores this field.";
}

function keyFieldHint(config: AiProviderReadSchema, keyless: boolean): string {
  if (keyless) {
    return "This provider is keyless. Any stored key is cleared when the provider is saved.";
  }
  if (config.source === "environment") {
    return "The active key comes from the server environment. Saving a key here creates a database override.";
  }
  if (config.key_hint) {
    return "Stored encrypted on the server. Leave blank to preserve the current key.";
  }
  return "No key stored. Paste one to configure this provider.";
}

function dimensionResult(value: string): { readonly value: number | null; readonly error: string | null } {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return { value: null, error: null };
  }
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 16 || parsed > 4096) {
    return {
      value: null,
      error: "Dimension must be a whole number between 16 and 4096.",
    };
  }
  return { value: parsed, error: null };
}

function ProviderTestResult({ result }: { readonly result: AiTestResultSchema }) {
  const dotTone: SettingsTone = result.ok ? "ok" : "error";
  return (
    <div
      className={result.ok ? "provider-test is-ok" : "provider-test is-failed"}
      role="status"
      aria-live="polite"
    >
      <span
        className={`settings-status-dot settings-status-dot--${dotTone}`}
        aria-hidden="true"
      />
      <div className="provider-test__copy">
        <p className="provider-test__head">
          <strong>{result.ok ? "Connection ok" : "Connection failed"}</strong>
          <span>
            {result.provider} · <code>{result.model}</code> · {formatNumber(result.latency_ms)} ms
          </span>
        </p>
        <p className="provider-test__detail">{result.detail}</p>
      </div>
    </div>
  );
}

function ProviderCardSkeleton() {
  return (
    <article className="provider-card provider-card--loading" aria-hidden="true">
      <span className="settings-skeleton settings-skeleton--short" />
      <span className="settings-skeleton settings-skeleton--title" />
      <span className="settings-skeleton" />
      <span className="settings-skeleton settings-skeleton--line" />
      <span className="settings-skeleton settings-skeleton--line is-short" />
      <span className="settings-skeleton settings-skeleton--field" />
      <span className="settings-skeleton settings-skeleton--field" />
    </article>
  );
}

function ProviderCard({ config }: { readonly config: AiProviderReadSchema }) {
  const purpose = config.purpose;
  const isEmbedding = purpose === "embedding";
  const purposeLabel = isEmbedding ? "Embedding" : "Chat";
  const options = isEmbedding ? EMBEDDING_PROVIDER_OPTIONS : CHAT_PROVIDER_OPTIONS;
  const fieldId = useId();
  const providerId = `${fieldId}-provider`;
  const modelId = `${fieldId}-model`;
  const baseUrlId = `${fieldId}-base-url`;
  const dimensionId = `${fieldId}-dimension`;
  const keyId = `${fieldId}-key`;
  const enabledId = `${fieldId}-enabled`;

  const queryClient = useQueryClient();
  const toast = useToast();

  const [provider, setProvider] = useState(config.provider);
  const [model, setModel] = useState(config.model);
  const [baseUrl, setBaseUrl] = useState(config.base_url ?? "");
  const [dimension, setDimension] = useState(
    config.dimension === null ? "" : String(config.dimension),
  );
  const [enabled, setEnabled] = useState(config.enabled);
  const [apiKey, setApiKey] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<AiTestResultSchema | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const updateProvider = useUpdateAiProvider({
    mutation: {
      onSuccess: async () => {
        setApiKey("");
        setFormError(null);
        setTestResult(null);
        setTestError(null);
        toast.success(`${purposeLabel} provider saved.`);
        await invalidateProviderQueries(queryClient);
      },
      onError: (error) => {
        setFormError(apiErrorMessage(error));
      },
    },
  });

  const clearKey = useClearAiProviderKey({
    mutation: {
      onSuccess: async () => {
        setApiKey("");
        setFormError(null);
        setTestResult(null);
        setTestError(null);
        toast.success(`${purposeLabel} API key cleared from the database.`);
        await invalidateProviderQueries(queryClient);
      },
      onError: (error) => {
        toast.error(apiErrorMessage(error));
      },
    },
  });

  const testProvider = useTestAiProvider({
    mutation: {
      onSuccess: (result) => {
        setTestResult(result);
        setTestError(null);
      },
      onError: (error) => {
        setTestResult(null);
        setTestError(apiErrorMessage(error));
      },
    },
  });

  const isSaving = updateProvider.isPending;
  const isTesting = testProvider.isPending;
  const isClearing = clearKey.isPending;
  const keyless = provider === "none" || provider === "hashing";
  const canClearKey = config.key_hint !== null && config.source === "database";
  const keyPlaceholder = config.key_hint
    ? `Leave blank to keep ${config.key_hint}`
    : "Paste a key";

  const resetFeedback = () => {
    setFormError(null);
    setTestResult(null);
    setTestError(null);
  };

  const handleProviderChange = (next: string) => {
    resetFeedback();
    setProvider(next);
    if (next === "none" || next === "hashing") {
      setApiKey("");
    }
    if (next === "none") {
      setEnabled(false);
      return;
    }
    setEnabled(true);
    if (next === "deepseek") {
      setModel((current) => (current.trim().length > 0 ? current : "deepseek-flash"));
      setBaseUrl((current) =>
        current.trim().length > 0 ? current : "https://api.deepseek.com",
      );
    } else if (next === "hashing") {
      setModel((current) => (current.trim().length > 0 ? current : "dendro-hash-384"));
      setDimension((current) => (current.trim().length > 0 ? current : "384"));
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedModel = model.trim();
    if (trimmedModel.length === 0) {
      setFormError("Model is required.");
      return;
    }
    const trimmedBaseUrl = baseUrl.trim();
    if (provider === "openai-compatible" && trimmedBaseUrl.length === 0) {
      setFormError("OpenAI-compatible providers require a base URL.");
      return;
    }
    const parsedDimension = dimensionResult(dimension);
    if (isEmbedding && parsedDimension.error) {
      setFormError(parsedDimension.error);
      return;
    }

    const data: AiProviderUpdateSchema = {
      provider,
      model: trimmedModel,
      base_url: trimmedBaseUrl.length > 0 ? trimmedBaseUrl : null,
      enabled,
    };
    if (isEmbedding) {
      data.dimension = parsedDimension.value;
    }
    const trimmedKey = apiKey.trim();
    if (trimmedKey.length > 0) {
      data.api_key = trimmedKey;
    }

    setFormError(null);
    updateProvider.mutate({ purpose, data });
  };

  return (
    <article className={`provider-card provider-card--${purpose}`}>
      <header className="provider-card__head">
        <div>
          <p className="provider-card__slot">{isEmbedding ? "Slot 02 · embedding" : "Slot 01 · chat"}</p>
          <h3 className="provider-card__title">
            {isEmbedding ? "Retrieval vectors" : "Ask and summaries"}
          </h3>
        </div>
        <div className="provider-card__badges">
          <Badge tone={sourceTone(config.source)} dot>
            {config.source}
          </Badge>
          <Badge tone={providerStateTone(config)} dot>
            {providerStateLabel(config)}
          </Badge>
        </div>
      </header>

      <p className="provider-card__copy">
        {isEmbedding
          ? "Stored embeddings for search. Hashing is deterministic and offline, with no key or network. OpenAI and OpenAI-compatible providers need a base URL, model, and key."
          : "Answers and memory summaries. DeepSeek uses deepseek-flash. An OpenAI-compatible endpoint can serve any chat model that follows the same API."}
      </p>

      <div className="provider-meta">
        <span className="provider-meta__item">
          <span className="provider-meta__label">Key</span>
          <code>{providerKeyLabel(config)}</code>
        </span>
        <span className="provider-meta__item">
          <span className="provider-meta__label">Updated</span>
          {config.updated_at ? (
            <time dateTime={config.updated_at}>{formatDateTime(config.updated_at)}</time>
          ) : (
            <span>not saved in the database</span>
          )}
        </span>
        <span className="provider-meta__item">
          <span className="provider-meta__label">Runtime</span>
          <span>{config.enabled ? "enabled" : "disabled"}</span>
        </span>
        {isEmbedding ? (
          <span className="provider-meta__item">
            <span className="provider-meta__label">Dimension</span>
            <span>{config.dimension ?? "—"}</span>
          </span>
        ) : null}
      </div>

      <form className="provider-form" onSubmit={handleSubmit} aria-busy={isSaving}>
        <div className="provider-form__grid">
          <label className="provider-field" htmlFor={providerId}>
            <span className="provider-field__label">Provider</span>
            <select
              id={providerId}
              className="provider-input provider-select"
              value={provider}
              onChange={(event) => handleProviderChange(event.target.value)}
              disabled={isSaving}
              aria-describedby={`${providerId}-hint`}
            >
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="provider-field__hint" id={`${providerId}-hint`}>
              {providerFieldHint(purpose)}
            </span>
          </label>

          <label className="provider-field" htmlFor={modelId}>
            <span className="provider-field__label">Model</span>
            <input
              id={modelId}
              className="provider-input"
              type="text"
              value={model}
              onChange={(event) => {
                setModel(event.target.value);
                resetFeedback();
              }}
              disabled={isSaving}
              required
              maxLength={128}
              spellCheck={false}
              autoCapitalize="none"
              aria-describedby={`${modelId}-hint`}
            />
            <span className="provider-field__hint" id={`${modelId}-hint`}>
              {modelFieldHint(purpose)}
            </span>
          </label>

          <label className="provider-field provider-field--wide" htmlFor={baseUrlId}>
            <span className="provider-field__label">Base URL</span>
            <input
              id={baseUrlId}
              className="provider-input"
              type="url"
              value={baseUrl}
              onChange={(event) => {
                setBaseUrl(event.target.value);
                resetFeedback();
              }}
              disabled={isSaving}
              placeholder="https://api.example.com/v1"
              maxLength={500}
              spellCheck={false}
              autoCapitalize="none"
              aria-describedby={`${baseUrlId}-hint`}
            />
            <span className="provider-field__hint" id={`${baseUrlId}-hint`}>
              {baseUrlFieldHint(purpose)}
            </span>
          </label>

          {isEmbedding ? (
            <label className="provider-field" htmlFor={dimensionId}>
              <span className="provider-field__label">Dimension</span>
              <input
                id={dimensionId}
                className="provider-input"
                type="number"
                min={16}
                max={4096}
                step={1}
                value={dimension}
                onChange={(event) => {
                  setDimension(event.target.value);
                  resetFeedback();
                }}
                disabled={isSaving}
                placeholder="384"
                aria-describedby={`${dimensionId}-hint`}
              />
              <span className="provider-field__hint" id={`${dimensionId}-hint`}>
                16–4096. Blank uses the server default, 384 for hashing.
              </span>
            </label>
          ) : null}

          <div className="provider-field provider-field--wide">
            <label className="provider-field__label" htmlFor={keyId}>
              API key
            </label>
            <div className="provider-key-row">
              <input
                id={keyId}
                className="provider-input"
                type="password"
                value={apiKey}
                onChange={(event) => {
                  setApiKey(event.target.value);
                  resetFeedback();
                }}
                disabled={isSaving || keyless}
                placeholder={keyPlaceholder}
                autoComplete="new-password"
                maxLength={500}
                spellCheck={false}
                autoCapitalize="none"
                aria-describedby={`${keyId}-hint`}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => clearKey.mutate({ purpose })}
                disabled={!canClearKey || isClearing || isSaving || isTesting}
                title={
                  config.key_hint !== null && config.source !== "database"
                    ? "Environment keys are managed on the server."
                    : undefined
                }
              >
                <Icon name="close" size={13} />
                {isClearing ? "Clearing…" : "Clear key"}
              </Button>
            </div>
            <span className="provider-field__hint" id={`${keyId}-hint`}>
              {keyFieldHint(config, keyless)}
            </span>
          </div>

          <label className="provider-toggle provider-field--wide" htmlFor={enabledId}>
            <input
              id={enabledId}
              type="checkbox"
              checked={enabled}
              onChange={(event) => {
                setEnabled(event.target.checked);
                resetFeedback();
              }}
              disabled={isSaving}
              aria-describedby={`${enabledId}-hint`}
            />
            <span>
              <strong>Enabled</strong>
              <span className="provider-field__hint" id={`${enabledId}-hint`}>
                Off disables this provider at runtime without deleting its configuration.
              </span>
            </span>
          </label>
        </div>

        {formError ? (
          <p className="provider-feedback provider-feedback--error" role="alert">
            <Icon name="info" size={14} />
            {formError}
          </p>
        ) : null}

        {testResult ? <ProviderTestResult result={testResult} /> : null}
        {testError ? (
          <p className="provider-feedback provider-feedback--error" role="alert">
            <Icon name="info" size={14} />
            {testError}
          </p>
        ) : null}
        {!testResult && !testError ? (
          <p className="provider-feedback provider-feedback--quiet">
            Test uses the saved configuration.
          </p>
        ) : null}

        <div className="provider-actions">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={isSaving || isTesting || isClearing}
          >
            <Icon name="check" size={14} />
            {isSaving ? "Saving…" : `Save ${purposeLabel.toLowerCase()}`}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => testProvider.mutate({ purpose })}
            disabled={isTesting || isSaving || isClearing}
          >
            <Icon name="spark" size={14} />
            {isTesting ? "Testing…" : "Test connection"}
          </Button>
        </div>
      </form>
    </article>
  );
}

function ModelProvidersPanel() {
  const settingsQuery = useGetAiSettings({ query: { staleTime: 30_000 } });
  const settings = settingsQuery.data;
  const vectorTone = configuredTone(settings?.vector_enabled ?? null);
  const toast = useToast();
  const queryClient = useQueryClient();
  const reindex = useReindexEmbeddings({
    mutation: {
      onSuccess: async (result) => {
        toast.success(
          `Re-embedded ${result.reindexed} chunks with ${result.model}.`,
        );
        await invalidateProviderQueries(queryClient);
      },
      onError: (error) => {
        toast.error(
          error instanceof Error ? error.message : "The re-index request failed.",
        );
      },
    },
  });

  let body: ReactNode;
  if (settingsQuery.isPending) {
    body = (
      <div
        className="provider-grid"
        aria-busy="true"
        aria-label="Reading model providers"
        role="status"
      >
        <ProviderCardSkeleton />
        <ProviderCardSkeleton />
      </div>
    );
  } else if (settingsQuery.isError || !settings) {
    body = (
      <div className="settings-inline-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>Provider settings did not answer.</strong>
          <p>{apiErrorMessage(settingsQuery.error)}</p>
        </div>
      </div>
    );
  } else {
    body = (
      <div className="provider-grid">
        <ProviderCard config={settings.chat} key={providerCardKey(settings.chat)} />
        <ProviderCard config={settings.embedding} key={providerCardKey(settings.embedding)} />
      </div>
    );
  }

  return (
    <Panel
      eyebrow="Intelligence · database-backed"
      title="Model providers."
      action={
        <div className="provider-panel__action">
          {settings?.reindex_required ? (
            <Badge tone="vermilion" dot>
              Re-index
            </Badge>
          ) : null}
          <Badge tone={toneToBadge(vectorTone)} dot>
            {vectorStatusLabel(settings?.vector_enabled)}
          </Badge>
        </div>
      }
      className="settings-panel settings-panel--providers reveal reveal-2"
    >
      <p className="settings-provider-intro">
        Configure the chat and embedding providers stored in the database. Saving
        reloads the runtime immediately. Keys are encrypted at rest, never returned
        to the browser, and never shown in this form.
      </p>

      {body}

      {settings?.reindex_required ? (
        <div className="provider-reindex" role="status">
          <Icon name="history" size={19} />
          <div>
            <strong>Re-index required</strong>
            <p>
              Existing chunks were embedded with a different model. New files use
              the current embedding model. Re-embed the library to make every
              current chunk searchable in the new vector space.
            </p>
          </div>
          <Button
            variant="ink"
            size="sm"
            className="provider-reindex__action"
            onClick={() => reindex.mutate()}
            disabled={reindex.isPending}
          >
            {reindex.isPending ? "Re-embedding…" : "Re-embed library"}
          </Button>
        </div>
      ) : null}

      <p className="settings-hint">
        Database settings take precedence over environment values.{" "}
        <code>DENDRO_DEEPSEEK_API_KEY</code> remains a fallback when no database chat
        key is stored. Saving an empty key field preserves the current key for providers
        that use one.
      </p>
    </Panel>
  );
}

/** Preferences, provider configuration, live service state, and archive controls. */
export function SettingsPage() {
  const { preference, setPreference } = useTheme();
  const toast = useToast();
  const queryClient = useQueryClient();

  const healthQuery = useGetHealth({ query: { staleTime: 30_000 } });
  const aiQuery = useGetAiStatus({ query: { staleTime: 60_000 } });
  const statsQuery = useGetStats({ query: { staleTime: 30_000 } });
  const providerFetching = useIsFetching({ queryKey: getGetAiSettingsQueryKey() });
  const health = healthQuery.data;
  const stats = statsQuery.data;

  const seedDemo = useSeedDemo({
    mutation: {
      onSuccess: (result) => {
        void queryClient.invalidateQueries();
        const summaryWord = result.summaries_created === 1 ? "summary" : "summaries";
        toast.success(
          `Seeded ${formatNumber(result.files_created)} files, ${formatNumber(result.memories_created)} memories, and ${formatNumber(result.summaries_created)} ${summaryWord}.`,
        );
      },
      onError: (error) => {
        toast.error(errorMessage(error));
      },
    },
  });

  let aiConfigured: boolean | null = null;
  if (aiQuery.data) {
    aiConfigured = aiQuery.data.configured;
  } else if (health) {
    aiConfigured = health.ai === "configured";
  }

  const aiTone = configuredTone(aiConfigured);
  const healthTone = systemTone(health, healthQuery.isError, healthQuery.isPending);
  const hasStats = stats !== undefined;
  const archiveHasData =
    stats !== undefined && stats.file_count + stats.memory_count > 0;
  const seedDisabled =
    seedDemo.isPending || statsQuery.isPending || archiveHasData;
  const isRefreshing =
    healthQuery.isFetching ||
    aiQuery.isFetching ||
    statsQuery.isFetching ||
    providerFetching > 0;
  const healthVersion = health?.version ?? "—";
  const aiProvider = aiQuery.data?.provider;
  const aiModel = aiQuery.data?.model;
  const embeddingProvider =
    aiQuery.data?.embedding_provider ?? health?.embedding_provider ?? "—";
  const embeddingModel = aiQuery.data?.embedding_model ?? "—";

  let seedDetail =
    "Adds a small set of files, memories, and one summary to this empty archive. Existing data is never overwritten.";
  if (archiveHasData) {
    seedDetail =
      "Unavailable: the archive already holds files or memories. Seeding never writes over existing work.";
  } else if (statsQuery.isPending) {
    seedDetail = "Checking the archive before seeding. The action unlocks when the counts are known.";
  } else if (statsQuery.isError) {
    seedDetail =
      "The counts could not be read. The API will still refuse to seed a non-empty archive.";
  }

  const copyApiBase = async () => {
    try {
      await navigator.clipboard.writeText("/api/v1");
      toast.success("API path copied to the clipboard.");
    } catch {
      toast.error("The clipboard is unavailable in this browser.");
    }
  };

  const handleRefresh = () => {
    void queryClient.invalidateQueries();
    toast.info("Refreshing the live archive state.");
  };

  return (
    <div className="page settings-page">
      <PageHeader
        eyebrow="Settings · reading room"
        title="Tune the archive."
        description="Choose the light you read by, configure model providers, inspect the live service state, and find the contract that binds the frontend to the archive."
        meta={<span>Theme stored in this browser · service state from /api/v1/health</span>}
        actions={
          <>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={isRefreshing}
            >
              <Icon name="ring" size={15} />
              Refresh state
            </Button>
            <ButtonLink to="/method" variant="ghost" size="sm">
              Read the method
              <Icon name="arrow-right" size={15} />
            </ButtonLink>
          </>
        }
      />

      <div className="settings-grid">
        <ModelProvidersPanel />

        <Panel
          eyebrow="Appearance"
          title="Choose the reading light."
          action={<Badge tone="moss">{preference}</Badge>}
          className="settings-panel settings-panel--theme settings-panel--wide reveal reveal-3"
        >
          <fieldset className="theme-choice">
            <legend className="visually-hidden">Archive theme</legend>
            {THEME_OPTIONS.map((option) => (
              <label
                className={
                  preference === option.value ? "theme-option is-selected" : "theme-option"
                }
                key={option.value}
              >
                <input
                  type="radio"
                  name="archive-theme"
                  value={option.value}
                  checked={preference === option.value}
                  onChange={() => setPreference(option.value)}
                />
                <span className="theme-option__top">
                  <span className="theme-option__label">{option.label}</span>
                  <span className="theme-option__check" aria-hidden="true">
                    <Icon name="check" size={13} />
                  </span>
                </span>
                <span className="theme-option__description">{option.description}</span>
                <span className="theme-swatches" aria-hidden="true">
                  {option.swatches.map((color) => (
                    <span key={color} style={{ backgroundColor: color }} />
                  ))}
                </span>
              </label>
            ))}
          </fieldset>
          <p className="settings-hint">
            The theme is applied before first paint, so reloading never flashes the wrong
            archive. Your choice is stored in <code>localStorage</code>.
          </p>
        </Panel>

        <Panel
          eyebrow="Intelligence"
          title="AI connection."
          action={
            <Badge tone={toneToBadge(aiTone)} dot>
              {configuredBadgeLabel(aiConfigured)}
            </Badge>
          }
          className="settings-panel settings-panel--narrow reveal reveal-4"
        >
          <div className="ai-status">
            <div className="ai-status__seal" aria-hidden="true">
              <Icon name="spark" size={26} />
            </div>
            <div>
              <p className="ai-status__state">
                {aiStateLabel(aiConfigured, aiProvider, aiModel)}
              </p>
              <p className="ai-status__detail">{aiDetailLabel(aiConfigured)}</p>
            </div>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Provider</dt>
              <dd>{aiProvider ?? "—"}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd><code>{aiModel ?? "—"}</code></dd>
            </div>
            <div>
              <dt>Configured</dt>
              <dd>{configuredLabel(aiConfigured)}</dd>
            </div>
            <div>
              <dt>Embedding provider</dt>
              <dd>{embeddingProvider}</dd>
            </div>
            <div>
              <dt>Embedding model</dt>
              <dd><code>{embeddingModel}</code></dd>
            </div>
            <div>
              <dt>Vector index</dt>
              <dd>{vectorLabel(aiQuery.data?.vector_enabled)}</dd>
            </div>
            <div>
              <dt>Status source</dt>
              <dd><code>GET /api/v1/ai/status</code></dd>
            </div>
          </dl>
          <p className="settings-hint">
            Runtime state comes from <code>GET /api/v1/ai/status</code>.
            Database-backed providers above take precedence over environment values;
            keys are never returned to the browser.
          </p>
        </Panel>

        <Panel
          eyebrow="System"
          title="Local installation."
          action={
            <Badge tone={toneToBadge(healthTone)} dot>
              {systemBadgeLabel(healthTone)}
            </Badge>
          }
          className="settings-panel settings-panel--wide reveal reveal-5"
        >
          <dl className="settings-list settings-list--system">
            <div>
              <dt>Application</dt>
              <dd>DendroMatrix {healthVersion}</dd>
            </div>
            <div>
              <dt>API status</dt>
              <dd>
                <SettingsDot tone={healthTone} />
                {apiStatusLabel(health, healthQuery.isError)}
              </dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>
                <SettingsDot tone={serviceTone(health?.database)} />
                {health?.database ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Cache</dt>
              <dd>
                <SettingsDot tone={serviceTone(health?.cache)} />
                {health?.cache ?? "—"}
              </dd>
            </div>
            <div>
              <dt>AI</dt>
              <dd>
                <SettingsDot tone={serviceTone(health?.ai)} />
                {aiHealthLabel(health?.ai)}
              </dd>
            </div>
            <div>
              <dt>Embedding</dt>
              <dd>{health?.embedding_provider ?? "—"}</dd>
            </div>
            <div>
              <dt>API base</dt>
              <dd>
                <code>/api/v1</code>
                <Button type="button" variant="ghost" size="sm" onClick={copyApiBase}>
                  <Icon name="copy" size={14} />
                  Copy
                </Button>
              </dd>
            </div>
            <div>
              <dt>API docs</dt>
              <dd>
                <a className="settings-text-link" href="/docs" target="_blank" rel="noreferrer">
                  /docs
                  <Icon name="external" size={13} />
                </a>
              </dd>
            </div>
            <div>
              <dt>Frontend</dt>
              <dd>React 19 + Vite</dd>
            </div>
          </dl>
          <p className="settings-hint">
            Health is read from <code>GET /api/v1/health</code>. If the cache is
            degraded, the API falls back to an in-process cache and reads still work.
          </p>
        </Panel>

        <Panel
          eyebrow="Archive"
          title="Live counts and seeding."
          action={
            <Badge tone={statsBadgeTone(hasStats, statsQuery.isError)} dot>
              {statsBadgeLabel(hasStats, statsQuery.isError)}
            </Badge>
          }
          className="settings-panel settings-panel--narrow reveal reveal-6"
        >
          <div
            className="settings-counts"
            aria-label="Archive counts"
            aria-busy={statsQuery.isPending}
          >
            <div>
              <span>Files</span>
              <strong>{stats ? formatNumber(stats.file_count) : "—"}</strong>
            </div>
            <div>
              <span>Memories</span>
              <strong>{stats ? formatNumber(stats.memory_count) : "—"}</strong>
              <small>{stats ? `${formatNumber(stats.active_memory_count)} active` : "reading"}</small>
            </div>
            <div>
              <span>Summaries</span>
              <strong>{stats ? formatNumber(stats.summary_count) : "—"}</strong>
            </div>
            <div>
              <span>Chunks</span>
              <strong>{stats ? formatNumber(stats.chunk_count) : "—"}</strong>
            </div>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Storage</dt>
              <dd>{stats ? formatBytes(stats.storage_bytes) : "—"}</dd>
            </div>
            <div>
              <dt>Oldest memory</dt>
              <dd>{stats?.oldest_memory_time ? formatDate(stats.oldest_memory_time) : "—"}</dd>
            </div>
            <div>
              <dt>Newest memory</dt>
              <dd>{stats?.newest_memory_time ? formatDate(stats.newest_memory_time) : "—"}</dd>
            </div>
          </dl>
          <div className="settings-seed">
            <div>
              <p className="settings-seed__title">Seed demo archive</p>
              <p className="settings-seed__detail">{seedDetail}</p>
            </div>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={() => seedDemo.mutate()}
              disabled={seedDisabled}
            >
              <Icon name="leaf" size={14} />
              {seedDemo.isPending ? "Seeding…" : "Seed demo archive"}
            </Button>
          </div>
          <p className="settings-hint">
            Seeding calls <code>POST /api/v1/demo/seed</code>. Counts, recent records,
            and the tree refresh when it finishes.
          </p>
        </Panel>

        <Panel
          eyebrow="Data & privacy"
          title="Local by default."
          className="settings-panel settings-panel--wide reveal reveal-6"
        >
          <ul className="settings-privacy">
            <li>
              <Icon name="database" size={17} />
              <div>
                <strong>Only this machine</strong>
                The API binds to 127.0.0.1 by default. The archive does not sync to a
                cloud account.
              </div>
            </li>
            <li>
              <Icon name="memory" size={17} />
              <div>
                <strong>No account layer</strong>
                There is no login or per-user permission model. Anyone with local access
                to the service can read the archive.
              </div>
            </li>
            <li>
              <Icon name="folder" size={17} />
              <div>
                <strong>Files under the data directory</strong>
                Uploaded files live under the configured data directory. PostgreSQL
                stores metadata, chunks, retrieval indexes, and provider settings.
              </div>
            </li>
            <li>
              <Icon name="spark" size={17} />
              <div>
                <strong>AI boundaries</strong>
                Chat and embedding providers are called only for summaries, Ask, and
                indexing. Chat providers receive retrieved passages, not the whole
                library. Keys stay on the server.
              </div>
            </li>
          </ul>
        </Panel>

        <Panel
          eyebrow="Contract"
          title="API documentation."
          className="settings-panel settings-panel--narrow reveal reveal-6"
        >
          <div className="docs-links">
            <a href="/docs" target="_blank" rel="noreferrer">
              <span className="docs-links__icon" aria-hidden="true">
                <Icon name="method" size={20} />
              </span>
              <span>
                <strong>Swagger UI · /docs</strong>
                <small>Explore the live API contract in the browser</small>
              </span>
              <Icon name="external" size={16} />
            </a>
          </div>
          <div className="code-snippet">
            <span className="figure-label">Generate the client</span>
            <code>bun run api:generate</code>
          </div>
          <p className="settings-hint">
            Generated hooks belong in <code>src/app/generated-apis-types/</code>. The
            shared mutator already throws <code>ApiError</code> on non-2xx responses.
          </p>
        </Panel>
      </div>

      <footer className="settings-foot">
        <span>DendroMatrix · local-first archive</span>
        <span aria-hidden="true">✦</span>
        <span>No account. No telemetry. One reader.</span>
      </footer>
    </div>
  );
}
