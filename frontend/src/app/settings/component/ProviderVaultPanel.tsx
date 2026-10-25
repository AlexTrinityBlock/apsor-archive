import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  getGetProviderRegistryQueryKey,
  useActivateProvider,
  useCreateProvider,
  useDeactivateProvider,
  useDeleteProvider,
  useGetProviderRegistry,
  useReindexEmbeddings,
  useTestProvider,
  useUpdateProvider,
} from "../../generated-apis-types";
import type {
  EmbeddingReindexSchema,
  ProviderCapabilityReadSchema,
  ProviderCreateSchema,
  ProviderReadSchema,
  ProviderRegistryReadSchema,
  ProviderTestResultSchema,
  ProviderUpdateSchema,
} from "../../generated-apis-types/schemas";
import { formatDateTime, formatNumber } from "../../../lib/format";
import {
  apiErrorMessage,
  isProviderKeyless,
  keySourceTone,
  providerConfiguredLabel,
  providerConfiguredTone,
  providerDisplayName,
  providerEndpointSummary,
  providerKeyLabel,
  providerKeySourceLabel,
  providerRegistryCardKey,
  providerStateLabel,
  providerStateTone,
  sourceLabel,
  sourceTone,
} from "./settings-utils";
import {
  invalidateProviderQueries,
  invalidateReindexQueries,
} from "./settings-invalidation";
import { SettingsDialog } from "./SettingsDialog";

type Capability = ProviderReadSchema["capability"];

const CAPABILITY_ORDER: readonly Capability[] = [
  "chat",
  "embedding",
  "web_search",
  "web_fetch",
];

const PROVIDER_DEFAULT_MODELS: Readonly<Record<string, string>> = {
  deepseek: "deepseek-flash",
  hashing: "apsor-hash-384",
  none: "none",
};

const KNOWN_DEFAULT_MODELS = new Set(Object.values(PROVIDER_DEFAULT_MODELS));

interface ProviderEditorDraft {
  readonly provider: string;
  readonly label: string;
  readonly model: string | null;
  readonly base_url: string | null;
  readonly dimension: number | null;
  readonly api_key: string | null;
  readonly clear_api_key: boolean;
  readonly activate: boolean;
}

interface ProviderEditorStateCreate {
  readonly mode: "create";
  readonly group: ProviderCapabilityReadSchema;
}

interface ProviderEditorStateEdit {
  readonly mode: "edit";
  readonly group: ProviderCapabilityReadSchema;
  readonly initial: ProviderReadSchema;
}

type ProviderEditorState = ProviderEditorStateCreate | ProviderEditorStateEdit;

interface ProviderTestState {
  readonly key: string;
  readonly result?: ProviderTestResultSchema;
  readonly error?: string;
}

function defaultModelFor(provider: string): string {
  return PROVIDER_DEFAULT_MODELS[provider] ?? "";
}

function nextModelFor(provider: string, current: string): string {
  const trimmed = current.trim();
  const nextDefault = PROVIDER_DEFAULT_MODELS[provider];
  if (nextDefault) {
    return trimmed.length === 0 || KNOWN_DEFAULT_MODELS.has(trimmed)
      ? nextDefault
      : current;
  }
  return KNOWN_DEFAULT_MODELS.has(trimmed) ? "" : current;
}

function keyPlaceholder(
  provider: string,
  keyless: boolean,
  keyHint: string | null,
): string {
  if (keyless || provider === "none") {
    return "No key required";
  }
  if (keyHint) {
    return `Leave blank to keep ${keyHint}`;
  }
  return "Paste a key";
}

function baseUrlError(value: string): string | null {
  if (value.length === 0) {
    return null;
  }
  if (value.length > 500) {
    return "Base URL must be 500 characters or fewer.";
  }
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "Base URL must start with http:// or https://.";
    }
    if (url.username.length > 0 || url.password.length > 0) {
      return "Base URL must not contain a username or password.";
    }
  } catch {
    return "Enter a complete URL, for example https://api.example.com/v1.";
  }
  return null;
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

function testTargetKey(capability: string, providerId: number): string {
  return `${capability}:${providerId}`;
}

function createPayload(draft: ProviderEditorDraft): ProviderCreateSchema {
  return {
    provider: draft.provider,
    label: draft.label,
    model: draft.model,
    base_url: draft.base_url,
    dimension: draft.dimension,
    api_key: draft.api_key,
    activate: draft.activate,
  };
}

function updatePayload(draft: ProviderEditorDraft): ProviderUpdateSchema {
  return {
    provider: draft.provider,
    label: draft.label,
    model: draft.model,
    base_url: draft.base_url,
    dimension: draft.dimension,
    api_key: draft.api_key,
    clear_api_key: draft.clear_api_key,
    activate: draft.activate,
  };
}

function ProviderTestLog({
  result,
  error,
  title,
}: {
  readonly result: ProviderTestResultSchema | null;
  readonly error: string | null;
  readonly title: string;
}) {
  if (!result && !error) {
    return null;
  }

  if (error) {
    return (
      <div className="vault-log is-error" role="alert">
        <span className="vault-log__line vault-log__line--info">
          {`> ${title} · saved configuration`}
        </span>
        <span className="vault-log__line vault-log__line--error">
          {"> FAILED · "}
          {error}
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
        {`> ${title} · saved configuration`}
      </span>
      <span
        className={
          result.ok
            ? "vault-log__line vault-log__line--ok"
            : "vault-log__line vault-log__line--error"
        }
      >
        {`> ${result.ok ? "OK" : "FAILED"} · ${providerDisplayName(result.provider)} · ${result.label} · ${result.latency_ms} ms`}
      </span>
      <span className="vault-log__line vault-log__line--detail">
        {`> ${result.detail}`}
      </span>
    </div>
  );
}

function ProviderFormCheck({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  readonly label: string;
  readonly hint: string;
  readonly checked: boolean;
  readonly disabled: boolean;
  readonly onChange: (checked: boolean) => void;
}) {
  return (
    <div className="registry-check-field">
      <label className="registry-check">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{label}</span>
      </label>
      <p className="settings-hint">{hint}</p>
    </div>
  );
}

function ProviderEditorDialog({
  group,
  initial,
  saving,
  error,
  onClose,
  onSubmit,
}: {
  readonly group: ProviderCapabilityReadSchema;
  readonly initial?: ProviderReadSchema;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (draft: ProviderEditorDraft) => void;
}) {
  const formId = useId();
  const fieldId = useId();
  const [provider, setProvider] = useState(
    initial?.provider ??
      group.allowed_providers.find((item) => item !== "none") ??
      group.allowed_providers[0] ??
      "none",
  );
  const [label, setLabel] = useState(initial?.label ?? "");
  const [model, setModel] = useState(
    initial?.model ?? defaultModelFor(initial?.provider ?? provider),
  );
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [dimension, setDimension] = useState(
    initial?.dimension === null || initial?.dimension === undefined
      ? ""
      : String(initial.dimension),
  );
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [activate, setActivate] = useState(
    initial ? initial.is_active : true,
  );
  const [formError, setFormError] = useState<string | null>(null);

  const keyless = group.keyless_providers.includes(provider);
  const isNone = provider === "none";
  const activeLocked = initial?.is_active === true;
  const canClearKey =
    initial !== undefined &&
    initial.id !== null &&
    initial.key_source === "database" &&
    !keyless;
  const keyDisabled = saving || keyless || isNone || clearKey;
  const keyHint = initial?.key_hint ?? null;

  const providerFieldId = `${fieldId}-provider`;
  const labelFieldId = `${fieldId}-label`;
  const modelFieldId = `${fieldId}-model`;
  const baseUrlFieldId = `${fieldId}-base-url`;
  const dimensionFieldId = `${fieldId}-dimension`;
  const keyFieldId = `${fieldId}-key`;
  let submitLabel = initial ? "Save provider" : "Add provider";
  if (saving) {
    submitLabel = "Saving…";
  }

  const handleProviderChange = (next: string) => {
    setFormError(null);
    setProvider(next);
    setClearKey(false);
    if (next === "none") {
      setModel("none");
      setBaseUrl("");
      setDimension("");
      setApiKey("");
      setActivate(false);
      return;
    }
    if (next === "hashing") {
      setBaseUrl("");
      setApiKey("");
      setDimension((current) => (current.trim().length === 0 ? "384" : current));
    }
    if (provider === "none") {
      setActivate(initial ? initial.is_active : true);
    }
    setModel((current) => nextModelFor(next, current));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedLabel = label.trim();
    if (trimmedLabel.length > 80) {
      setFormError("Label must be 80 characters or fewer.");
      return;
    }
    const trimmedModel = model.trim();
    if (group.supports_model && !isNone && trimmedModel.length === 0) {
      setFormError("Model is required for this provider.");
      return;
    }
    const trimmedBaseUrl = baseUrl.trim();
    if (provider === "openai-compatible" && trimmedBaseUrl.length === 0) {
      setFormError("OpenAI-compatible providers require a base URL.");
      return;
    }
    const urlError = baseUrlError(trimmedBaseUrl);
    if (urlError) {
      setFormError(urlError);
      return;
    }
    const parsedDimension = dimensionResult(dimension);
    if (group.supports_dimension && parsedDimension.error) {
      setFormError(parsedDimension.error);
      return;
    }
    const trimmedKey = apiKey.trim();
    if (trimmedKey.length > 500) {
      setFormError("API key must be 500 characters or fewer.");
      return;
    }

    let modelValue: string | null = null;
    if (group.supports_model) {
      modelValue = isNone ? "none" : trimmedModel;
    }
    let baseValue: string | null = null;
    if (!isNone && provider !== "hashing" && trimmedBaseUrl.length > 0) {
      baseValue = trimmedBaseUrl;
    }

    setFormError(null);
    onSubmit({
      provider,
      label: trimmedLabel,
      model: modelValue,
      base_url: baseValue,
      dimension:
        group.supports_dimension && !isNone ? parsedDimension.value : null,
      api_key: trimmedKey.length > 0 ? trimmedKey : null,
      clear_api_key: clearKey,
      activate: isNone ? false : activate,
    });
  };

  return (
    <SettingsDialog
      eyebrow={`Settings · ${group.title.toLowerCase()} provider`}
      title={initial ? "Edit provider" : "Add provider"}
      description={group.description}
      onClose={onClose}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="ink"
            size="sm"
            disabled={saving}
          >
            {submitLabel}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="registry-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <div className="registry-form__grid">
          <label className="field" htmlFor={providerFieldId}>
            <span className="field-label">Provider</span>
            <select
              id={providerFieldId}
              className="select"
              value={provider}
              onChange={(event) => handleProviderChange(event.target.value)}
              disabled={saving}
              data-autofocus
            >
              {group.allowed_providers.map((option) => (
                <option key={option} value={option}>
                  {providerDisplayName(option)}
                </option>
              ))}
            </select>
            <span className="field-help">
              Allowed kinds come from the API for this capability.
            </span>
          </label>

          <label className="field" htmlFor={labelFieldId}>
            <span className="field-label">Label</span>
            <input
              id={labelFieldId}
              className="input"
              type="text"
              value={label}
              onChange={(event) => {
                setLabel(event.target.value);
                setFormError(null);
              }}
              maxLength={80}
              placeholder={providerDisplayName(provider)}
              disabled={saving}
            />
            <span className="field-help">
              An optional display name. Blank uses the provider kind.
            </span>
          </label>

          {group.supports_model ? (
            <label className="field" htmlFor={modelFieldId}>
              <span className="field-label">Model</span>
              <input
                id={modelFieldId}
                className="input registry-input"
                type="text"
                value={model}
                onChange={(event) => {
                  setModel(event.target.value);
                  setFormError(null);
                }}
                maxLength={128}
                spellCheck={false}
                autoCapitalize="none"
                disabled={saving || isNone}
                placeholder={
                  group.capability === "embedding"
                    ? "text-embedding-3-small"
                    : "deepseek-flash"
                }
              />
              <span className="field-help">
                {group.capability === "embedding"
                  ? "Recorded for new chunks. Changing it requires re-embedding."
                  : "The model id sent to this provider."}
              </span>
            </label>
          ) : null}

          <label className="field" htmlFor={baseUrlFieldId}>
            <span className="field-label">Base URL</span>
            <input
              id={baseUrlFieldId}
              className="input registry-input"
              type="url"
              value={baseUrl}
              onChange={(event) => {
                setBaseUrl(event.target.value);
                setFormError(null);
              }}
              maxLength={500}
              spellCheck={false}
              autoCapitalize="none"
              disabled={saving || isNone || provider === "hashing"}
              placeholder={
                group.default_base_url ?? "https://api.example.com/v1"
              }
            />
            <span className="field-help">
              Leave blank to use the provider default
              {group.default_base_url ? ` (${group.default_base_url})` : ""}.
            </span>
          </label>

          {group.supports_dimension ? (
            <label className="field" htmlFor={dimensionFieldId}>
              <span className="field-label">Dimension</span>
              <input
                id={dimensionFieldId}
                className="input registry-input"
                type="number"
                min={16}
                max={4096}
                step={1}
                value={dimension}
                onChange={(event) => {
                  setDimension(event.target.value);
                  setFormError(null);
                }}
                disabled={saving || isNone}
                placeholder="Provider default"
              />
              <span className="field-help">
                16–4096. Blank uses the provider default, 384 for hashing.
              </span>
            </label>
          ) : null}

          <div className="field registry-form__wide">
            <label className="field-label" htmlFor={keyFieldId}>
              API key
            </label>
            <input
              id={keyFieldId}
              className="input registry-input"
              type="password"
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                setClearKey(false);
                setFormError(null);
              }}
              placeholder={keyPlaceholder(provider, keyless, keyHint)}
              autoComplete="new-password"
              maxLength={500}
              spellCheck={false}
              autoCapitalize="none"
              disabled={keyDisabled}
            />
            <span className="field-help">
              {keyless
                ? "This provider needs no key. Saving clears any stored key for the row."
                : "Encrypted on the server and never returned to this page. Leave blank to keep the current key."}
            </span>
          </div>

          {canClearKey ? (
            <div className="registry-form__wide">
              <ProviderFormCheck
                label="Clear stored key"
                hint="Removes the database key. Environment fallback may still apply to the active provider."
                checked={clearKey}
                disabled={saving || apiKey.trim().length > 0}
                onChange={setClearKey}
              />
            </div>
          ) : null}

          <div className="registry-form__wide">
            <ProviderFormCheck
              label="Activate after saving"
              hint={
                activeLocked
                  ? "This row is active. Use Deactivate in the registry to turn it off."
                  : "Makes this row the only active provider for this capability."
              }
              checked={activate}
              disabled={saving || isNone || activeLocked}
              onChange={setActivate}
            />
          </div>
        </div>

        {group.capability === "web_search" ||
        group.capability === "web_fetch" ? (
          <p className="settings-hint">
            Web search and web fetch use separate credentials. Paste this
            capability&apos;s Tavily key here even if the other capability uses
            the same value.
          </p>
        ) : null}

        {formError ?? error ? (
          <p className="vault-feedback vault-feedback--error" role="alert">
            <Icon name="info" size={14} />
            {formError ?? error}
          </p>
        ) : null}
      </form>
    </SettingsDialog>
  );
}

function ActiveProviderCard({
  group,
  provider,
  busy,
  onEdit,
  onDeactivate,
  onTest,
}: {
  readonly group: ProviderCapabilityReadSchema;
  readonly provider: ProviderReadSchema;
  readonly busy: boolean;
  readonly onEdit: (provider: ProviderReadSchema) => void;
  readonly onDeactivate: () => void;
  readonly onTest: (provider: ProviderReadSchema) => void;
}) {
  const keyless = isProviderKeyless(provider, group.keyless_providers);
  const runtimeFallback = provider.id === null;
  const summary = providerEndpointSummary(
    provider,
    group.supports_model,
    group.supports_dimension,
  );

  return (
    <article
      className={
        runtimeFallback ? "registry-active is-fallback" : "registry-active"
      }
    >
      <div className="registry-active__head">
        <div className="registry-active__heading">
          <p className="mono-label">
            {runtimeFallback ? "Runtime fallback" : "Active provider"}
          </p>
          <h3 className="registry-active__title">
            {provider.label || providerDisplayName(provider.provider)}
          </h3>
          <p className="registry-active__runtime">
            {summary.map((part, index) => (
              <span key={`${part}-${index}`}>
                {index > 0 ? <span aria-hidden="true">·</span> : null}
                <code>{part}</code>
              </span>
            ))}
          </p>
        </div>
        <div className="registry-active__badges">
          <Badge tone={sourceTone(provider.source)} dot>
            {sourceLabel(provider.source)}
          </Badge>
          <Badge tone={keySourceTone(provider, keyless)} dot>
            {providerKeySourceLabel(provider, keyless)}
          </Badge>
          <Badge tone={providerConfiguredTone(provider)} dot>
            {providerConfiguredLabel(provider)}
          </Badge>
        </div>
      </div>

      <dl className="meta-grid registry-meta">
        <div className="meta-item">
          <dt className="meta-key">Provider</dt>
          <dd className="meta-value">
            {providerDisplayName(provider.provider)}
          </dd>
        </div>
        {group.supports_model ? (
          <div className="meta-item">
            <dt className="meta-key">Model</dt>
            <dd className="meta-value">{provider.model ?? "—"}</dd>
          </div>
        ) : null}
        <div className="meta-item">
          <dt className="meta-key">Base URL</dt>
          <dd className="meta-value" title={provider.base_url ?? undefined}>
            {provider.base_url ?? "Provider default"}
          </dd>
        </div>
        {group.supports_dimension ? (
          <div className="meta-item">
            <dt className="meta-key">Dimension</dt>
            <dd className="meta-value">
              {provider.dimension === null
                ? "Provider default"
                : `${provider.dimension}-D`}
            </dd>
          </div>
        ) : null}
        <div className="meta-item">
          <dt className="meta-key">Key</dt>
          <dd className="meta-value" title={providerKeyLabel(provider, keyless)}>
            {providerKeyLabel(provider, keyless)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Key source</dt>
          <dd className="meta-value">
            {providerKeySourceLabel(provider, keyless)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Configured</dt>
          <dd className="meta-value">
            {providerConfiguredLabel(provider)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Updated</dt>
          <dd className="meta-value">
            {provider.updated_at ? (
              <time dateTime={provider.updated_at}>
                {formatDateTime(provider.updated_at)}
              </time>
            ) : (
              "Runtime fallback"
            )}
          </dd>
        </div>
      </dl>

      {runtimeFallback ? (
        <p className="registry-active__note">
          No saved row is active. This state comes from the server environment
          or the built-in defaults; add and activate a provider to override it.
        </p>
      ) : null}

      {provider.id !== null ? (
        <div className="registry-row__actions">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onTest(provider)}
            disabled={busy}
          >
            <Icon name="spark" size={13} />
            Test connection
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onEdit(provider)}
            disabled={busy}
          >
            <Icon name="pencil" size={13} />
            Edit
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDeactivate}
            disabled={busy}
          >
            <Icon name="stop" size={13} />
            Deactivate
          </Button>
        </div>
      ) : null}
    </article>
  );
}

function SavedProviderRow({
  group,
  provider,
  busy,
  onEdit,
  onActivate,
  onDeactivate,
  onDelete,
  onTest,
}: {
  readonly group: ProviderCapabilityReadSchema;
  readonly provider: ProviderReadSchema;
  readonly busy: boolean;
  readonly onEdit: (provider: ProviderReadSchema) => void;
  readonly onActivate: (provider: ProviderReadSchema) => void;
  readonly onDeactivate: () => void;
  readonly onDelete: (provider: ProviderReadSchema) => void;
  readonly onTest: (provider: ProviderReadSchema) => void;
}) {
  const keyless = isProviderKeyless(provider, group.keyless_providers);
  const summary = providerEndpointSummary(
    provider,
    group.supports_model,
    group.supports_dimension,
  );

  return (
    <article
      className={
        provider.is_active ? "registry-row is-active" : "registry-row"
      }
    >
      <div className="registry-row__main">
        <div className="registry-row__title">
          <span className="registry-row__name">
            {provider.label || providerDisplayName(provider.provider)}
          </span>
          {provider.is_active ? (
            <Badge tone="moss" dot>
              Active
            </Badge>
          ) : (
            <Badge tone="neutral">Saved</Badge>
          )}
          <Badge tone={providerStateTone(provider)}>
            {providerStateLabel(provider)}
          </Badge>
        </div>
        <p className="registry-row__meta">
          {summary.map((part, index) => (
            <span key={`${part}-${index}`}>
              {index > 0 ? <span aria-hidden="true">·</span> : null}
              <code>{part}</code>
            </span>
          ))}
        </p>
        <p className="registry-row__state">
          <span>{providerKeyLabel(provider, keyless)}</span>
          <span aria-hidden="true">·</span>
          <span>{providerKeySourceLabel(provider, keyless)}</span>
          <span aria-hidden="true">·</span>
          <span>{sourceLabel(provider.source)}</span>
          {provider.updated_at ? (
            <>
              <span aria-hidden="true">·</span>
              <time dateTime={provider.updated_at}>
                {formatDateTime(provider.updated_at)}
              </time>
            </>
          ) : null}
        </p>
      </div>

      {provider.id !== null ? (
        <div className="registry-row__actions">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onTest(provider)}
            disabled={busy}
          >
            <Icon name="spark" size={13} />
            Test
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onEdit(provider)}
            disabled={busy}
          >
            <Icon name="pencil" size={13} />
            Edit
          </Button>
          {provider.is_active ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onDeactivate}
              disabled={busy}
            >
              <Icon name="stop" size={13} />
              Deactivate
            </Button>
          ) : (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onActivate(provider)}
              disabled={busy}
            >
              <Icon name="check" size={13} />
              Activate
            </Button>
          )}
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={() => onDelete(provider)}
            disabled={busy}
          >
            <Icon name="trash" size={13} />
            Delete
          </Button>
        </div>
      ) : null}
    </article>
  );
}

function RegistrySection({
  group,
  index,
  busy,
  testState,
  extra,
  onAdd,
  onEdit,
  onActivate,
  onDeactivate,
  onDelete,
  onTest,
}: {
  readonly group: ProviderCapabilityReadSchema;
  readonly index: number;
  readonly busy: boolean;
  readonly testState: ProviderTestState | null;
  readonly extra?: ReactNode;
  readonly onAdd: () => void;
  readonly onEdit: (provider: ProviderReadSchema) => void;
  readonly onActivate: (provider: ProviderReadSchema) => void;
  readonly onDeactivate: () => void;
  readonly onDelete: (provider: ProviderReadSchema) => void;
  readonly onTest: (provider: ProviderReadSchema) => void;
}) {
  const active = group.active;
  const sectionTest =
    testState && testState.key.startsWith(`${group.capability}:`)
      ? testState
      : null;

  return (
    <section className="registry-section" aria-labelledby={`${group.capability}-title`}>
      <div className="registry-section__head">
        <div className="registry-section__heading">
          <p className="mono-label">
            {String(index).padStart(2, "0")} · {group.capability}
          </p>
          <h3 className="registry-section__title" id={`${group.capability}-title`}>
            {group.title}
          </h3>
          <p className="registry-section__copy">{group.description}</p>
        </div>
        <div className="registry-section__actions">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onAdd}
            disabled={busy}
          >
            <Icon name="plus" size={13} />
            Add provider
          </Button>
        </div>
      </div>

      {active ? (
        <ActiveProviderCard
          group={group}
          provider={active}
          busy={busy}
          onEdit={onEdit}
          onDeactivate={onDeactivate}
          onTest={onTest}
        />
      ) : (
        <p className="registry-empty">
          No provider state is available for this capability yet.
        </p>
      )}

      <div className="registry-list">
        <div className="registry-list__head">
          <p className="mono-label">Saved providers</p>
          <span className="registry-list__count">
            {group.providers.length} saved
          </span>
        </div>
        {group.providers.length === 0 ? (
          <p className="registry-empty">
            No saved rows. Add one to pin this capability to a provider.
          </p>
        ) : (
          group.providers.map((provider) => (
            <SavedProviderRow
              key={providerRegistryCardKey(group.capability, provider)}
              group={group}
              provider={provider}
              busy={busy}
              onEdit={onEdit}
              onActivate={onActivate}
              onDeactivate={onDeactivate}
              onDelete={onDelete}
              onTest={onTest}
            />
          ))
        )}
      </div>

      <ProviderTestLog
        title={group.title}
        result={sectionTest?.result ?? null}
        error={sectionTest?.error ?? null}
      />

      {extra}
    </section>
  );
}

function ProviderSectionSkeleton() {
  return (
    <section className="registry-section registry-section--loading" aria-hidden="true">
      <div className="registry-section__head">
        <div className="registry-section__heading">
          <span className="settings-skeleton settings-skeleton--title" />
          <span className="settings-skeleton settings-skeleton--line is-short" />
        </div>
        <span className="settings-skeleton settings-skeleton--badge" />
      </div>
      <span className="settings-skeleton settings-skeleton--field" />
      <span className="settings-skeleton settings-skeleton--line" />
    </section>
  );
}

function ReindexAction({
  enabled,
  pending,
  result,
  error,
  onRequest,
}: {
  readonly enabled: boolean;
  readonly pending: boolean;
  readonly result: EmbeddingReindexSchema | null;
  readonly error: string | null;
  readonly onRequest: () => void;
}) {
  return (
    <div className="registry-reindex">
      <div className="registry-reindex__copy">
        <p className="mono-label">Vector maintenance</p>
        <p className="registry-reindex__text">
          Recompute every current chunk with the active embedding provider after
          changing its model or dimension.
        </p>
      </div>
      <div className="registry-reindex__actions">
        <Button
          type="button"
          variant="ink"
          size="sm"
          onClick={onRequest}
          disabled={!enabled || pending}
        >
          <Icon name="history" size={13} />
          {pending ? "Re-embedding…" : "Re-index embeddings"}
        </Button>
      </div>
      {result ? (
        <p className="reindex__result" role="status">
          <Icon name="check" size={14} />
          Re-embedded {formatNumber(result.reindexed)} chunks ·{" "}
          {formatNumber(result.dimension)}-D ·{" "}
          {formatNumber(result.elapsed_ms)} ms.
        </p>
      ) : null}
      {error ? (
        <p className="vault-feedback vault-feedback--error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ProviderDialogs({
  editor,
  editorError,
  createPending,
  updatePending,
  deleteTarget,
  deletePending,
  reindexOpen,
  reindexPending,
  onCloseEditor,
  onCreate,
  onUpdate,
  onCloseDelete,
  onConfirmDelete,
  onCloseReindex,
  onConfirmReindex,
}: {
  readonly editor: ProviderEditorState | null;
  readonly editorError: string | null;
  readonly createPending: boolean;
  readonly updatePending: boolean;
  readonly deleteTarget: ProviderReadSchema | null;
  readonly deletePending: boolean;
  readonly reindexOpen: boolean;
  readonly reindexPending: boolean;
  readonly onCloseEditor: () => void;
  readonly onCreate: (
    group: ProviderCapabilityReadSchema,
    draft: ProviderEditorDraft,
  ) => void;
  readonly onUpdate: (
    group: ProviderCapabilityReadSchema,
    providerId: number,
    draft: ProviderEditorDraft,
  ) => void;
  readonly onCloseDelete: () => void;
  readonly onConfirmDelete: (
    capability: Capability,
    providerId: number,
  ) => void;
  readonly onCloseReindex: () => void;
  readonly onConfirmReindex: () => void;
}) {
  return (
    <>
      {editor ? (
        <ProviderEditorDialog
          key={editor.mode === "edit" ? (editor.initial.id ?? "new") : "new"}
          group={editor.group}
          initial={editor.mode === "edit" ? editor.initial : undefined}
          saving={editor.mode === "create" ? createPending : updatePending}
          error={editorError}
          onClose={onCloseEditor}
          onSubmit={(draft) => {
            if (editor.mode === "create") {
              onCreate(editor.group, draft);
              return;
            }
            if (editor.initial.id !== null) {
              onUpdate(editor.group, editor.initial.id, draft);
            }
          }}
        />
      ) : null}

      {deleteTarget ? (
        <SettingsDialog
          eyebrow="Settings · provider registry"
          title="Delete this provider?"
          description={`${deleteTarget.label || providerDisplayName(deleteTarget.provider)} will be removed from the ${deleteTarget.capability.replace("_", " ")} slot.`}
          onClose={onCloseDelete}
          actions={
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onCloseDelete}
                disabled={deletePending}
                data-autofocus
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => {
                  if (deleteTarget.id !== null) {
                    onConfirmDelete(
                      deleteTarget.capability,
                      deleteTarget.id,
                    );
                  }
                }}
                disabled={deletePending}
              >
                {deletePending ? "Deleting…" : "Delete provider"}
              </Button>
            </>
          }
        >
          <p className="settings-lede">
            {deleteTarget.is_active
              ? "This row is active. Deleting it falls the capability back to the server environment or built-in defaults."
              : "This removes only the saved row. Other providers in this capability are unchanged."}
          </p>
        </SettingsDialog>
      ) : null}

      {reindexOpen ? (
        <SettingsDialog
          eyebrow="Settings · embedding"
          title="Re-embed every current chunk?"
          description="Re-indexing recomputes stored vectors with the active embedding provider. It runs synchronously and may take a while."
          onClose={onCloseReindex}
          actions={
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onCloseReindex}
                disabled={reindexPending}
                data-autofocus
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={onConfirmReindex}
                disabled={reindexPending}
              >
                {reindexPending ? "Re-embedding…" : "Start re-index"}
              </Button>
            </>
          }
        >
          <p className="settings-lede">
            The embedding model and dimension must match the active provider
            before new files are ingested.
          </p>
        </SettingsDialog>
      ) : null}
    </>
  );
}

/** Four capability slots, their saved rows, and their encrypted key state. */
export function ProviderVaultPanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const registryQuery = useGetProviderRegistry({
    query: { staleTime: 30_000 },
  });
  const [editor, setEditor] = useState<ProviderEditorState | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProviderReadSchema | null>(
    null,
  );
  const [testState, setTestState] = useState<ProviderTestState | null>(null);
  const [reindexOpen, setReindexOpen] = useState(false);
  const [reindexResult, setReindexResult] =
    useState<EmbeddingReindexSchema | null>(null);
  const [reindexError, setReindexError] = useState<string | null>(null);

  const applyRegistry = async (
    data: ProviderRegistryReadSchema,
  ): Promise<void> => {
    queryClient.setQueryData(getGetProviderRegistryQueryKey(), data);
    await invalidateProviderQueries(queryClient);
  };

  const createMutation = useCreateProvider({
    mutation: {
      onMutate: () => setEditorError(null),
      onSuccess: async (data) => {
        await applyRegistry(data);
        setEditor(null);
        toast.success("Provider added to the registry.");
      },
      onError: (error) => {
        setEditorError(apiErrorMessage(error));
      },
    },
  });

  const updateMutation = useUpdateProvider({
    mutation: {
      onMutate: () => setEditorError(null),
      onSuccess: async (data) => {
        await applyRegistry(data);
        setEditor(null);
        toast.success("Provider updated.");
      },
      onError: (error) => {
        setEditorError(apiErrorMessage(error));
      },
    },
  });

  const activateMutation = useActivateProvider({
    mutation: {
      onSuccess: async (data) => {
        await applyRegistry(data);
        toast.success("Provider activated.");
      },
      onError: (error) => {
        toast.error(apiErrorMessage(error));
      },
    },
  });

  const deactivateMutation = useDeactivateProvider({
    mutation: {
      onSuccess: async (data) => {
        await applyRegistry(data);
        toast.success("Provider deactivated. The runtime falls back.");
      },
      onError: (error) => {
        toast.error(apiErrorMessage(error));
      },
    },
  });

  const deleteMutation = useDeleteProvider({
    mutation: {
      onSuccess: async (data) => {
        await applyRegistry(data);
        setDeleteTarget(null);
        toast.success("Provider deleted.");
      },
      onError: (error) => {
        toast.error(apiErrorMessage(error));
      },
    },
  });

  const testMutation = useTestProvider({
    mutation: {
      onMutate: (variables) => {
        setTestState({
          key: testTargetKey(variables.capability, variables.providerId),
        });
      },
      onSuccess: (result, variables) => {
        setTestState({
          key: testTargetKey(variables.capability, variables.providerId),
          result,
        });
      },
      onError: (error, variables) => {
        setTestState({
          key: testTargetKey(variables.capability, variables.providerId),
          error: apiErrorMessage(error),
        });
      },
    },
  });

  const reindexMutation = useReindexEmbeddings({
    mutation: {
      onSuccess: async (data) => {
        setReindexResult(data);
        setReindexError(null);
        setReindexOpen(false);
        toast.success(
          `Re-embedded ${formatNumber(data.reindexed)} chunks with ${data.model}.`,
        );
        await invalidateReindexQueries(queryClient);
      },
      onError: (error) => {
        const message = apiErrorMessage(error);
        setReindexError(message);
        setReindexOpen(false);
        toast.error(message);
      },
    },
  });

  const registry = registryQuery.data;
  const orderedGroups = registry
    ? CAPABILITY_ORDER.flatMap((capability) => {
        const group = registry.capabilities.find(
          (item) => item.capability === capability,
        );
        return group ? [group] : [];
      })
    : [];

  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    activateMutation.isPending ||
    deactivateMutation.isPending ||
    deleteMutation.isPending ||
    testMutation.isPending;

  const openEditor = (next: ProviderEditorState) => {
    setEditorError(null);
    setEditor(next);
  };

  const handleDeactivate = (capability: Capability) => {
    deactivateMutation.mutate({ capability });
  };

  const reindexExtra = (
    <ReindexAction
      enabled={registry?.vector_enabled === true && !busy}
      pending={reindexMutation.isPending}
      result={reindexResult}
      error={reindexError}
      onRequest={() => {
        setReindexError(null);
        setReindexOpen(true);
      }}
    />
  );

  let body: ReactNode;
  if (registryQuery.isPending) {
    body = (
      <div
        className="registry-stack"
        role="status"
        aria-busy="true"
        aria-label="Reading provider registry"
      >
        {CAPABILITY_ORDER.map((capability) => (
          <ProviderSectionSkeleton key={capability} />
        ))}
      </div>
    );
  } else if (registryQuery.isError || !registry) {
    body = (
      <div className="settings-inline-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>The provider registry did not answer.</strong>
          <p>{apiErrorMessage(registryQuery.error)}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void registryQuery.refetch()}
            disabled={registryQuery.isFetching}
          >
            <Icon name="ring" size={14} />
            {registryQuery.isFetching ? "Retrying…" : "Retry"}
          </Button>
        </div>
      </div>
    );
  } else {
    body = (
      <div className="registry-stack">
        {orderedGroups.map((group, index) => (
          <RegistrySection
            key={group.capability}
            group={group}
            index={index + 1}
            busy={busy}
            testState={testState}
            extra={group.capability === "embedding" ? reindexExtra : undefined}
            onAdd={() => openEditor({ mode: "create", group })}
            onEdit={(provider) =>
              openEditor({ mode: "edit", group, initial: provider })
            }
            onActivate={(provider) => {
              if (provider.id !== null) {
                activateMutation.mutate({
                  capability: group.capability,
                  providerId: provider.id,
                });
              }
            }}
            onDeactivate={() => handleDeactivate(group.capability)}
            onDelete={(provider) => setDeleteTarget(provider)}
            onTest={(provider) => {
              if (provider.id !== null) {
                testMutation.mutate({
                  capability: group.capability,
                  providerId: provider.id,
                });
              }
            }}
          />
        ))}
      </div>
    );
  }

  return (
    <>
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="database" size={16} />
            Provider registry
          </span>
        }
        action={
          <div className="settings-panel__badges">
            {registry?.reindex_required ? (
              <Badge tone="ochre" dot>
                Re-index required
              </Badge>
            ) : null}
            <Badge tone={registry?.vector_enabled ? "moss" : "neutral"} dot>
              {vectorBadgeLabel(
                registryQuery.isPending,
                registry?.vector_enabled,
                registryQuery.isError,
              )}
            </Badge>
          </div>
        }
        className="settings-panel"
      >
        <p className="settings-lede">
          Four capability slots stored in PostgreSQL: chat, embedding, web
          search, and web fetch. One row is active per slot; saving reloads the
          runtime immediately. Web search and web fetch use{" "}
          <strong>separate credentials</strong>; if both should use the same
          Tavily key, paste it into each section. Keys are encrypted at rest,
          never returned to the browser, and never prefilled here.
        </p>

        {body}

        {registry?.reindex_required ? (
          <div className="settings-callout settings-callout--warn" role="status">
            <Icon name="history" size={18} />
            <div>
              <strong>Re-index required</strong>
              <p>
                Existing chunks were embedded with a different model. New files
                use the active embedding provider. Re-embed the library from the
                embedding section or System diagnostics to align the corpus.
              </p>
            </div>
          </div>
        ) : null}

        <p className="settings-hint">
          Database rows take precedence over environment fallbacks. Leaving a
          key field blank preserves the stored key. Use Deactivate to fall back
          to the server environment or built-in defaults for one capability.
        </p>
      </Panel>

      <ProviderDialogs
        editor={editor}
        editorError={editorError}
        createPending={createMutation.isPending}
        updatePending={updateMutation.isPending}
        deleteTarget={deleteTarget}
        deletePending={deleteMutation.isPending}
        reindexOpen={reindexOpen}
        reindexPending={reindexMutation.isPending}
        onCloseEditor={() => {
          if (!createMutation.isPending && !updateMutation.isPending) {
            setEditor(null);
            setEditorError(null);
          }
        }}
        onCreate={(group, draft) =>
          createMutation.mutate({
            capability: group.capability,
            data: createPayload(draft),
          })
        }
        onUpdate={(group, providerId, draft) =>
          updateMutation.mutate({
            capability: group.capability,
            providerId,
            data: updatePayload(draft),
          })
        }
        onCloseDelete={() => {
          if (!deleteMutation.isPending) {
            setDeleteTarget(null);
          }
        }}
        onConfirmDelete={(capability, providerId) =>
          deleteMutation.mutate({ capability, providerId })
        }
        onCloseReindex={() => {
          if (!reindexMutation.isPending) {
            setReindexOpen(false);
          }
        }}
        onConfirmReindex={() => reindexMutation.mutate()}
      />
    </>
  );
}
