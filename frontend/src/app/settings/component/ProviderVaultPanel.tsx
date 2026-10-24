import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  getGetAiSettingsQueryKey,
  useClearAiProviderKey,
  useGetAiSettings,
  useTestAiProvider,
  useUpdateAiProvider,
} from "../../generated-apis-types";
import type {
  AiProviderReadSchema,
  AiProviderUpdateSchema,
  AiSettingsReadSchema,
  AiTestResultSchema,
} from "../../generated-apis-types/schemas";
import { formatDateTime } from "../../../lib/format";
import {
  apiErrorMessage,
  providerCardKey,
  providerKeyLabel,
  providerKeySourceLabel,
  providerStateLabel,
  providerStateTone,
  sourceLabel,
  sourceTone,
} from "./settings-utils";
import { invalidateProviderQueries } from "./settings-invalidation";
import { SwitchField } from "./SwitchField";

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

const KEYLESS_PROVIDERS = new Set(["none", "hashing"]);

const PROVIDER_DEFAULT_MODELS: Readonly<Record<string, string>> = {
  deepseek: "deepseek-flash",
  hashing: "dendro-hash-384",
  none: "none",
};

const KNOWN_DEFAULT_MODELS = new Set(Object.values(PROVIDER_DEFAULT_MODELS));

function modelForProvider(next: string, current: string): string {
  const trimmed = current.trim();
  const nextDefault = PROVIDER_DEFAULT_MODELS[next];
  if (nextDefault) {
    return trimmed.length === 0 || KNOWN_DEFAULT_MODELS.has(trimmed)
      ? nextDefault
      : current;
  }
  return KNOWN_DEFAULT_MODELS.has(trimmed) ? "" : current;
}

function dimensionForProvider(
  previous: string,
  next: string,
  current: string,
): string {
  const trimmed = current.trim();
  if (next === "hashing") {
    return trimmed.length === 0 || previous === "openai" || previous === "openai-compatible"
      ? "384"
      : current;
  }
  if (next === "openai" || next === "openai-compatible" || next === "none") {
    return previous === "hashing" && trimmed === "384" ? "" : current;
  }
  return current;
}

function keyPlaceholder(
  config: AiProviderReadSchema,
  keyless: boolean,
): string {
  if (keyless) {
    return "No key required";
  }
  if (config.key_hint) {
    return `Leave blank to keep ${config.key_hint}`;
  }
  return "Paste a key";
}

function clearKeyTitle(keyless: boolean, canClear: boolean): string | undefined {
  if (canClear) {
    return undefined;
  }
  return keyless
    ? "This provider needs no key."
    : "Only a database key can be cleared here.";
}

function vectorBadgeLabel(
  pending: boolean,
  enabled: boolean | undefined,
  isError: boolean,
): string {
  if (pending) {
    return "Reading vector";
  }
  if (isError) {
    return "Vector unavailable";
  }
  return enabled ? "Vector on" : "Vector off";
}

function buildProviderPayload(
  provider: string,
  model: string,
  baseUrl: string,
  dimension: string,
  enabled: boolean,
  apiKey: string,
  isEmbedding: boolean,
): { readonly data: AiProviderUpdateSchema | null; readonly error: string | null } {
  const trimmedModel = model.trim();
  if (provider !== "none" && trimmedModel.length === 0) {
    return { data: null, error: "Model is required." };
  }
  const trimmedBaseUrl = baseUrl.trim();
  if (provider === "openai-compatible" && trimmedBaseUrl.length === 0) {
    return {
      data: null,
      error: "OpenAI-compatible providers require a base URL.",
    };
  }
  const urlError = baseUrlError(trimmedBaseUrl);
  if (urlError) {
    return { data: null, error: urlError };
  }
  const parsedDimension = dimensionResult(dimension);
  if (isEmbedding && parsedDimension.error) {
    return { data: null, error: parsedDimension.error };
  }

  const data: AiProviderUpdateSchema = {
    provider,
    model: trimmedModel.length > 0 ? trimmedModel : "none",
    base_url: trimmedBaseUrl.length > 0 ? trimmedBaseUrl : null,
    enabled: provider === "none" ? false : enabled,
  };
  if (isEmbedding) {
    data.dimension = parsedDimension.value;
  }
  const trimmedKey = apiKey.trim();
  if (trimmedKey.length > 0) {
    data.api_key = trimmedKey;
  }
  return { data, error: null };
}

function providerOptions(
  purpose: AiProviderReadSchema["purpose"],
  current: string,
): readonly ProviderOption[] {
  const options =
    purpose === "embedding" ? EMBEDDING_PROVIDER_OPTIONS : CHAT_PROVIDER_OPTIONS;
  return options.some((option) => option.value === current)
    ? options
    : [{ value: current, label: current }, ...options];
}

function providerFieldHint(purpose: AiProviderReadSchema["purpose"]): string {
  if (purpose === "chat") {
    return "DeepSeek uses its hosted endpoint. OpenAI-compatible requires a base URL.";
  }
  return "Hashing is deterministic and offline. OpenAI-compatible requires a base URL.";
}

function modelFieldHint(purpose: AiProviderReadSchema["purpose"]): string {
  if (purpose === "chat") {
    return "The model id sent to the chat provider.";
  }
  return "Recorded for new chunks. Changing it requires re-embedding the library.";
}

function baseUrlFieldHint(purpose: AiProviderReadSchema["purpose"]): string {
  if (purpose === "chat") {
    return "Required for openai-compatible. Leave blank for the DeepSeek default.";
  }
  return "Required for openai-compatible. Hashing ignores this field.";
}

function baseUrlPlaceholder(provider: string): string {
  if (provider === "hashing") {
    return "Not used by hashing";
  }
  if (provider === "none") {
    return "Provider disabled";
  }
  if (provider === "deepseek") {
    return "https://api.deepseek.com (default)";
  }
  return "https://api.example.com/v1";
}

function keyFieldHint(config: AiProviderReadSchema, keyless: boolean): string {
  if (keyless) {
    return "This provider needs no key. Saving clears any stored key for the slot.";
  }
  if (config.key_source === "environment") {
    return "The active key comes from the server environment. Saving a key here stores a database override.";
  }
  if (config.key_hint) {
    return "Stored encrypted on the server and never returned to this page. Leave blank to keep the current key.";
  }
  return "No key stored. Paste one to configure this provider.";
}

function dimensionResult(
  value: string,
): { readonly value: number | null; readonly error: string | null } {
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

function baseUrlError(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "Base URL must start with http:// or https://.";
    }
  } catch {
    return "Enter a complete URL, for example https://api.example.com/v1.";
  }
  return null;
}

function ProviderTestLog({
  result,
  error,
}: {
  readonly result: AiTestResultSchema | null;
  readonly error: string | null;
}) {
  if (!result && !error) {
    return null;
  }

  if (error) {
    return (
      <div className="vault-log is-error" role="alert">
        <span className="vault-log__line vault-log__line--info">
          {"> provider test · saved configuration"}
        </span>
        <span className="vault-log__line vault-log__line--error">
          {"> FAILED · {error}"}
        </span>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  return (
    <div
      className={result.ok ? "vault-log is-ok" : "vault-log is-error"}
      role="status"
      aria-live="polite"
    >
      <span className="vault-log__line vault-log__line--info">
        {"> provider test · saved configuration"}
      </span>
      <span
        className={
          result.ok
            ? "vault-log__line vault-log__line--ok"
            : "vault-log__line vault-log__line--error"
        }
      >
        {`> ${result.ok ? "OK" : "FAILED"} · ${result.provider} · ${result.model} · ${result.latency_ms} ms`}
      </span>
      <span className="vault-log__line vault-log__line--detail">
        {`> ${result.detail}`}
      </span>
    </div>
  );
}

function ProviderCard({ config }: { readonly config: AiProviderReadSchema }) {
  const purpose = config.purpose;
  const isEmbedding = purpose === "embedding";
  const purposeLabel = isEmbedding ? "Embedding" : "Chat";
  const options = providerOptions(purpose, config.provider);
  const fieldId = useId();
  const providerId = `${fieldId}-provider`;
  const modelId = `${fieldId}-model`;
  const baseUrlId = `${fieldId}-base-url`;
  const dimensionId = `${fieldId}-dimension`;
  const keyId = `${fieldId}-key`;

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
  const [confirmingClear, setConfirmingClear] = useState(false);

  const applySettings = (data: AiSettingsReadSchema) => {
    queryClient.setQueryData(getGetAiSettingsQueryKey(), data);
  };

  const updateProvider = useUpdateAiProvider({
    mutation: {
      onSuccess: async (data) => {
        applySettings(data);
        setApiKey("");
        setFormError(null);
        setTestResult(null);
        setTestError(null);
        setConfirmingClear(false);
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
      onSuccess: async (data) => {
        applySettings(data);
        setApiKey("");
        setFormError(null);
        setTestResult(null);
        setTestError(null);
        setConfirmingClear(false);
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
  const keyless = KEYLESS_PROVIDERS.has(provider);
  const canClearKey = config.key_source === "database" && !keyless;
  const keyInputPlaceholder = keyPlaceholder(config, keyless);

  const resetFeedback = () => {
    setFormError(null);
    setTestResult(null);
    setTestError(null);
    setConfirmingClear(false);
  };

  const handleProviderChange = (next: string) => {
    resetFeedback();
    setProvider(next);
    if (next === "none" || next === "hashing") {
      setApiKey("");
    }
    if (next === "none") {
      setEnabled(false);
      setBaseUrl("");
      setModel((current) => modelForProvider(next, current));
      setDimension((current) => dimensionForProvider(provider, next, current));
      return;
    }
    setEnabled(true);
    setModel((current) => modelForProvider(next, current));
    setDimension((current) => dimensionForProvider(provider, next, current));
    if (next === "hashing") {
      setBaseUrl("");
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload = buildProviderPayload(
      provider,
      model,
      baseUrl,
      dimension,
      enabled,
      apiKey,
      isEmbedding,
    );
    if (!payload.data) {
      setFormError(payload.error);
      return;
    }
    setFormError(null);
    updateProvider.mutate({ purpose, data: payload.data });
  };

  return (
    <article className="vault-card">
      <header className="vault-card__head">
        <div className="vault-card__heading">
          <p className="mono-label">
            {isEmbedding ? "Slot 02 · Embedding" : "Slot 01 · Chat"}
          </p>
          <h3 className="vault-card__title">
            {isEmbedding ? "Embedding vectors" : "Chat inference"}
          </h3>
          <p className="vault-card__runtime">
            <code>{config.provider}</code>
            <span aria-hidden="true">·</span>
            <code>{config.model}</code>
            {isEmbedding ? (
              <>
                <span aria-hidden="true">·</span>
                <span>
                  {config.dimension === null
                    ? "default dimension"
                    : `${config.dimension}-D`}
                </span>
              </>
            ) : null}
          </p>
        </div>
        <div className="vault-card__badges">
          <Badge tone={sourceTone(config.source)} dot>
            {sourceLabel(config.source)}
          </Badge>
          <Badge tone={providerStateTone(config)} dot>
            {providerStateLabel(config)}
          </Badge>
        </div>
      </header>

      <p className="vault-card__copy">
        {isEmbedding
          ? "Stored vectors for hybrid search. Hashing is deterministic and offline with no key or network. OpenAI and OpenAI-compatible providers need a model and key; compatible endpoints also need a base URL."
          : "Answers and memory summaries. DeepSeek uses its hosted endpoint. Any OpenAI-compatible endpoint can serve a chat model that follows the same API."}
      </p>

      <dl className="meta-grid vault-meta">
        <div className="meta-item">
          <dt className="meta-key">Key</dt>
          <dd className="meta-value" title={providerKeyLabel(config)}>
            {providerKeyLabel(config)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Key source</dt>
          <dd className="meta-value">{providerKeySourceLabel(config)}</dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Enabled</dt>
          <dd className="meta-value">{config.enabled ? "Yes" : "No"}</dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Updated</dt>
          <dd className="meta-value">
            {config.updated_at ? (
              <time dateTime={config.updated_at}>
                {formatDateTime(config.updated_at)}
              </time>
            ) : (
              "Not saved"
            )}
          </dd>
        </div>
      </dl>

      <form
        className="vault-form"
        onSubmit={handleSubmit}
        aria-busy={isSaving}
        noValidate
      >
        <div className="vault-form__grid">
          <label className="field" htmlFor={providerId}>
            <span className="field-label">Provider</span>
            <select
              id={providerId}
              className="select"
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
            <span className="field-help" id={`${providerId}-hint`}>
              {providerFieldHint(purpose)}
            </span>
          </label>

          <label className="field" htmlFor={modelId}>
            <span className="field-label">Model</span>
            <input
              id={modelId}
              className="input vault-input"
              type="text"
              value={model}
              onChange={(event) => {
                setModel(event.target.value);
                resetFeedback();
              }}
              disabled={isSaving || provider === "none"}
              maxLength={128}
              spellCheck={false}
              autoCapitalize="none"
              aria-describedby={`${modelId}-hint`}
            />
            <span className="field-help" id={`${modelId}-hint`}>
              {modelFieldHint(purpose)}
            </span>
          </label>

          <label className="field vault-field--wide" htmlFor={baseUrlId}>
            <span className="field-label">Base URL</span>
            <input
              id={baseUrlId}
              className="input vault-input"
              type="url"
              value={baseUrl}
              onChange={(event) => {
                setBaseUrl(event.target.value);
                resetFeedback();
              }}
              disabled={isSaving || provider === "hashing" || provider === "none"}
              placeholder={baseUrlPlaceholder(provider)}
              maxLength={500}
              spellCheck={false}
              autoCapitalize="none"
              aria-describedby={`${baseUrlId}-hint`}
            />
            <span className="field-help" id={`${baseUrlId}-hint`}>
              {baseUrlFieldHint(purpose)}
            </span>
          </label>

          {isEmbedding ? (
            <label className="field" htmlFor={dimensionId}>
              <span className="field-label">Dimension</span>
              <input
                id={dimensionId}
                className="input vault-input"
                type="number"
                min={16}
                max={4096}
                step={1}
                value={dimension}
                onChange={(event) => {
                  setDimension(event.target.value);
                  resetFeedback();
                }}
                disabled={isSaving || provider === "none"}
                placeholder="384"
                aria-describedby={`${dimensionId}-hint`}
              />
              <span className="field-help" id={`${dimensionId}-hint`}>
                16–4096. Blank uses the provider default, 384 for hashing.
              </span>
            </label>
          ) : null}

          <div className="field vault-field--wide">
            <label className="field-label" htmlFor={keyId}>
              API key
            </label>
            <div className="vault-keyrow">
              <input
                id={keyId}
                className="input vault-input"
                type="password"
                value={apiKey}
                onChange={(event) => {
                  setApiKey(event.target.value);
                  resetFeedback();
                }}
                disabled={isSaving || keyless}
                placeholder={keyInputPlaceholder}
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
                onClick={() => setConfirmingClear(true)}
                disabled={!canClearKey || isClearing || isSaving || isTesting}
                title={clearKeyTitle(keyless, canClearKey)}
              >
                <Icon name="close" size={13} />
                {isClearing ? "Clearing…" : "Clear key"}
              </Button>
            </div>
            <span className="field-help" id={`${keyId}-hint`}>
              {keyFieldHint(config, keyless)}
            </span>
          </div>

          {confirmingClear ? (
            <div className="vault-confirm" role="status">
              <span>
                Remove the stored {purposeLabel.toLowerCase()} key? The provider
                will stop working until a new key is saved.
              </span>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => clearKey.mutate({ purpose })}
                disabled={isClearing || isSaving}
              >
                {isClearing ? "Clearing…" : "Confirm clear"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingClear(false)}
                disabled={isClearing}
              >
                Cancel
              </Button>
            </div>
          ) : null}

          <div className="vault-field--wide">
            <SwitchField
              label="Enabled"
              hint="Off disables this provider at runtime without deleting its configuration."
              checked={enabled}
              disabled={isSaving || provider === "none"}
              onChange={(next) => {
                setEnabled(next);
                resetFeedback();
              }}
            />
          </div>
        </div>

        {formError ? (
          <p className="vault-feedback vault-feedback--error" role="alert">
            <Icon name="info" size={14} />
            {formError}
          </p>
        ) : null}

        <ProviderTestLog result={testResult} error={testError} />

        {!testResult && !testError ? (
          <p className="vault-feedback vault-feedback--quiet">
            The connection test uses the saved configuration.
          </p>
        ) : null}

        <div className="vault-actions">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => testProvider.mutate({ purpose })}
            disabled={isTesting || isSaving || isClearing}
          >
            <Icon name="spark" size={14} />
            {isTesting ? "Testing…" : "Test connection"}
          </Button>
          <Button
            type="submit"
            variant="ink"
            size="sm"
            disabled={isSaving || isTesting || isClearing}
          >
            <Icon name="check" size={14} />
            {isSaving ? "Saving…" : `Save ${purposeLabel.toLowerCase()}`}
          </Button>
        </div>
      </form>
    </article>
  );
}

function ProviderCardSkeleton() {
  return (
    <article className="vault-card vault-card--loading" aria-hidden="true">
      <div className="vault-card__head">
        <span className="settings-skeleton settings-skeleton--title" />
        <span className="settings-skeleton settings-skeleton--badge" />
      </div>
      <div className="vault-card__body">
        <span className="settings-skeleton settings-skeleton--line" />
        <span className="settings-skeleton settings-skeleton--line is-short" />
        <span className="settings-skeleton settings-skeleton--field" />
        <span className="settings-skeleton settings-skeleton--field" />
      </div>
    </article>
  );
}

/** Both database-backed provider slots and their encrypted key state. */
export function ProviderVaultPanel() {
  const settingsQuery = useGetAiSettings({ query: { staleTime: 30_000 } });
  const settings = settingsQuery.data;

  let body: ReactNode;
  if (settingsQuery.isPending) {
    body = (
      <div
        className="vault-grid"
        role="status"
        aria-busy="true"
        aria-label="Reading provider settings"
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
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void settingsQuery.refetch()}
            disabled={settingsQuery.isFetching}
          >
            <Icon name="ring" size={14} />
            {settingsQuery.isFetching ? "Retrying…" : "Retry"}
          </Button>
        </div>
      </div>
    );
  } else {
    body = (
      <div className="vault-grid">
        <ProviderCard config={settings.chat} key={providerCardKey(settings.chat)} />
        <ProviderCard
          config={settings.embedding}
          key={providerCardKey(settings.embedding)}
        />
      </div>
    );
  }

  return (
    <Panel
      title={
        <span className="settings-panel__title">
          <Icon name="database" size={16} />
          AI provider vault
        </span>
      }
      action={
        <div className="settings-panel__badges">
          {settings?.reindex_required ? (
            <Badge tone="ochre" dot>
              Re-index required
            </Badge>
          ) : null}
          <Badge tone={settings?.vector_enabled ? "moss" : "neutral"} dot>
            {vectorBadgeLabel(
              settingsQuery.isPending,
              settings?.vector_enabled,
              settingsQuery.isError,
            )}
          </Badge>
        </div>
      }
      className="settings-panel"
    >
      <p className="settings-lede">
        Two provider slots stored in PostgreSQL. Saving reloads the runtime
        immediately. Keys are encrypted at rest, never returned to the browser,
        and never shown in this form.
      </p>

      {body}

      {settings?.reindex_required ? (
        <div className="settings-callout settings-callout--warn" role="status">
          <Icon name="history" size={18} />
          <div>
            <strong>Re-index required</strong>
            <p>
              Existing chunks were embedded with a different model or dimension.
              New files use the saved embedding provider. Re-embed the library
              from System diagnostics to align the current corpus.
            </p>
          </div>
        </div>
      ) : null}

      <p className="settings-hint">
        Database values take precedence over environment values. The DeepSeek
        environment key remains a fallback when no database chat key is stored.
        Leaving the key field blank preserves the stored key.
      </p>
    </Panel>
  );
}
