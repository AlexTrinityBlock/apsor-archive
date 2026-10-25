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
import { useI18n, type Translate } from "../../i18n";
import {
  apiErrorMessage,
  isProviderKeyless,
  keySourceTone,
  providerConfiguredLabel,
  providerConfiguredTone,
  providerDisplayName,
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
  t: Translate,
): string {
  if (keyless || provider === "none") {
    return t("settings.providers.keyPlaceholderNoKey");
  }
  if (keyHint) {
    return t("settings.providers.keyPlaceholderKeep", { hint: keyHint });
  }
  return t("settings.providers.keyPlaceholderPaste");
}

function baseUrlError(value: string, t: Translate): string | null {
  if (value.length === 0) {
    return null;
  }
  if (value.length > 500) {
    return t("settings.providers.errors.baseUrlMax");
  }
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return t("settings.providers.errors.baseUrlProtocol");
    }
    if (url.username.length > 0 || url.password.length > 0) {
      return t("settings.providers.errors.baseUrlCredentials");
    }
  } catch {
    return t("settings.providers.errors.baseUrlInvalid");
  }
  return null;
}

function dimensionResult(
  value: string,
  t: Translate,
): { readonly value: number | null; readonly error: string | null } {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return { value: null, error: null };
  }
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 16 || parsed > 4096) {
    return {
      value: null,
      error: t("settings.providers.errors.dimension"),
    };
  }
  return { value: parsed, error: null };
}

function vectorBadgeLabel(
  pending: boolean,
  enabled: boolean | undefined,
  isError: boolean,
  t: Translate,
): string {
  if (pending) {
    return t("settings.providers.vectorReading");
  }
  if (isError) {
    return t("settings.providers.vectorUnavailable");
  }
  return enabled
    ? t("settings.providers.vectorOn")
    : t("settings.providers.vectorOff");
}

function capabilityLabel(capability: Capability, t: Translate): string {
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

function providerSummaryParts(
  config: ProviderReadSchema,
  supportsModel: boolean,
  supportsDimension: boolean,
  t: Translate,
): readonly string[] {
  const parts: string[] = [providerDisplayName(config.provider)];
  if (supportsModel && config.model) {
    parts.push(config.model);
  }
  if (config.base_url) {
    parts.push(config.base_url);
  }
  if (supportsDimension) {
    parts.push(
      config.dimension === null
        ? t("settings.providers.providerDefault")
        : t("settings.providers.dimension", {
            dimension: String(config.dimension),
          }),
    );
  }
  return parts;
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
  const { t, formatNumber } = useI18n();
  if (!result && !error) {
    return null;
  }

  if (error) {
    return (
      <div className="vault-log is-error" role="alert">
        <span className="vault-log__line vault-log__line--info">
          {t("settings.providers.testLogConfig", { title })}
        </span>
        <span className="vault-log__line vault-log__line--error">
          {t("settings.providers.testLogFailed")}
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
        {t("settings.providers.testLogConfig", { title })}
      </span>
      <span
        className={
          result.ok
            ? "vault-log__line vault-log__line--ok"
            : "vault-log__line vault-log__line--error"
        }
      >
        {t("settings.providers.testLogResult", {
          status: result.ok
            ? t("settings.providers.testStatusOk")
            : t("settings.providers.testStatusFailed"),
          provider: providerDisplayName(result.provider),
          label: result.label,
          latency: formatNumber(result.latency_ms),
        })}
      </span>
      <span className="vault-log__line vault-log__line--detail">
        {t("settings.providers.testLogDetail", { detail: result.detail })}
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
  const { t } = useI18n();
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
  let submitLabel = initial
    ? t("settings.providers.submitSave")
    : t("settings.providers.submitAdd");
  if (saving) {
    submitLabel = t("settings.providers.saving");
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
      setFormError(t("settings.providers.errors.labelMax"));
      return;
    }
    const trimmedModel = model.trim();
    if (group.supports_model && !isNone && trimmedModel.length === 0) {
      setFormError(t("settings.providers.errors.modelRequired"));
      return;
    }
    const trimmedBaseUrl = baseUrl.trim();
    if (provider === "openai-compatible" && trimmedBaseUrl.length === 0) {
      setFormError(t("settings.providers.errors.baseUrlRequired"));
      return;
    }
    const urlError = baseUrlError(trimmedBaseUrl, t);
    if (urlError) {
      setFormError(urlError);
      return;
    }
    const parsedDimension = dimensionResult(dimension, t);
    if (group.supports_dimension && parsedDimension.error) {
      setFormError(parsedDimension.error);
      return;
    }
    const trimmedKey = apiKey.trim();
    if (trimmedKey.length > 500) {
      setFormError(t("settings.providers.errors.apiKeyMax"));
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
      eyebrow={t("settings.providers.editorEyebrow", {
        capability: capabilityLabel(group.capability, t),
      })}
      title={
        initial
          ? t("settings.providers.editTitle")
          : t("settings.providers.addTitle")
      }
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
            {t("settings.common.cancel")}
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
            <span className="field-label">
              {t("settings.providers.fieldProvider")}
            </span>
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
              {t("settings.providers.providerHelp")}
            </span>
          </label>

          <label className="field" htmlFor={labelFieldId}>
            <span className="field-label">
              {t("settings.providers.fieldLabel")}
            </span>
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
              {t("settings.providers.labelHelp")}
            </span>
          </label>

          {group.supports_model ? (
            <label className="field" htmlFor={modelFieldId}>
              <span className="field-label">
                {t("settings.providers.fieldModel")}
              </span>
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
                  ? t("settings.providers.modelHelpEmbedding")
                  : t("settings.providers.modelHelp")}
              </span>
            </label>
          ) : null}

          <label className="field" htmlFor={baseUrlFieldId}>
            <span className="field-label">
              {t("settings.providers.fieldBaseUrl")}
            </span>
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
              {group.default_base_url
                ? t("settings.providers.baseUrlHelpDefault", {
                    url: group.default_base_url,
                  })
                : t("settings.providers.baseUrlHelp")}
            </span>
          </label>

          {group.supports_dimension ? (
            <label className="field" htmlFor={dimensionFieldId}>
              <span className="field-label">
                {t("settings.providers.fieldDimension")}
              </span>
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
                placeholder={t("settings.providers.providerDefault")}
              />
              <span className="field-help">
                {t("settings.providers.dimensionHelp")}
              </span>
            </label>
          ) : null}

          <div className="field registry-form__wide">
            <label className="field-label" htmlFor={keyFieldId}>
              {t("settings.providers.fieldApiKey")}
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
              placeholder={keyPlaceholder(provider, keyless, keyHint, t)}
              autoComplete="new-password"
              maxLength={500}
              spellCheck={false}
              autoCapitalize="none"
              disabled={keyDisabled}
            />
            <span className="field-help">
              {keyless
                ? t("settings.providers.keyHelpKeyless")
                : t("settings.providers.keyHelp")}
            </span>
          </div>

          {canClearKey ? (
            <div className="registry-form__wide">
              <ProviderFormCheck
                label={t("settings.providers.clearKey")}
                hint={t("settings.providers.clearKeyHint")}
                checked={clearKey}
                disabled={saving || apiKey.trim().length > 0}
                onChange={setClearKey}
              />
            </div>
          ) : null}

          <div className="registry-form__wide">
            <ProviderFormCheck
              label={t("settings.providers.activateAfterSave")}
              hint={
                activeLocked
                  ? t("settings.providers.activateHintLocked")
                  : t("settings.providers.activateHint")
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
            {t("settings.providers.webCredentialsNote")}
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
  const { t, formatDateTime } = useI18n();
  const keyless = isProviderKeyless(provider, group.keyless_providers);
  const runtimeFallback = provider.id === null;
  const summary = providerSummaryParts(
    provider,
    group.supports_model,
    group.supports_dimension,
    t,
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
            {runtimeFallback
              ? t("settings.providers.runtimeFallback")
              : t("settings.providers.activeProvider")}
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
          <dt className="meta-key">{t("settings.providers.metaProvider")}</dt>
          <dd className="meta-value">
            {providerDisplayName(provider.provider)}
          </dd>
        </div>
        {group.supports_model ? (
          <div className="meta-item">
            <dt className="meta-key">{t("settings.providers.metaModel")}</dt>
            <dd className="meta-value">{provider.model ?? "—"}</dd>
          </div>
        ) : null}
        <div className="meta-item">
          <dt className="meta-key">{t("settings.providers.metaBaseUrl")}</dt>
          <dd className="meta-value" title={provider.base_url ?? undefined}>
            {provider.base_url ?? t("settings.providers.providerDefault")}
          </dd>
        </div>
        {group.supports_dimension ? (
          <div className="meta-item">
            <dt className="meta-key">{t("settings.providers.metaDimension")}</dt>
            <dd className="meta-value">
              {provider.dimension === null
                ? t("settings.providers.providerDefault")
                : t("settings.providers.dimension", {
                    dimension: String(provider.dimension),
                  })}
            </dd>
          </div>
        ) : null}
        <div className="meta-item">
          <dt className="meta-key">{t("settings.providers.metaKey")}</dt>
          <dd className="meta-value" title={providerKeyLabel(provider, keyless)}>
            {providerKeyLabel(provider, keyless)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("settings.providers.metaKeySource")}</dt>
          <dd className="meta-value">
            {providerKeySourceLabel(provider, keyless)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("settings.providers.metaConfigured")}</dt>
          <dd className="meta-value">
            {providerConfiguredLabel(provider)}
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("settings.providers.metaUpdated")}</dt>
          <dd className="meta-value">
            {provider.updated_at ? (
              <time dateTime={provider.updated_at}>
                {formatDateTime(provider.updated_at)}
              </time>
            ) : (
              t("settings.providers.runtimeFallback")
            )}
          </dd>
        </div>
      </dl>

      {runtimeFallback ? (
        <p className="registry-active__note">
          {t("settings.providers.fallbackNote")}
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
            {t("settings.providers.testConnection")}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onEdit(provider)}
            disabled={busy}
          >
            <Icon name="pencil" size={13} />
            {t("settings.providers.edit")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDeactivate}
            disabled={busy}
          >
            <Icon name="stop" size={13} />
            {t("settings.providers.deactivate")}
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
  const { t, formatDateTime } = useI18n();
  const keyless = isProviderKeyless(provider, group.keyless_providers);
  const summary = providerSummaryParts(
    provider,
    group.supports_model,
    group.supports_dimension,
    t,
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
              {t("settings.providers.active")}
            </Badge>
          ) : (
            <Badge tone="neutral">{t("settings.providers.saved")}</Badge>
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
            {t("settings.providers.test")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onEdit(provider)}
            disabled={busy}
          >
            <Icon name="pencil" size={13} />
            {t("settings.providers.edit")}
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
              {t("settings.providers.deactivate")}
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
              {t("settings.providers.activate")}
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
            {t("settings.providers.delete")}
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
  const { t, formatNumber } = useI18n();
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
            {String(index).padStart(2, "0")} ·{" "}
            {capabilityLabel(group.capability, t)}
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
            {t("settings.providers.add")}
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
          {t("settings.providers.noProviderState")}
        </p>
      )}

      <div className="registry-list">
        <div className="registry-list__head">
          <p className="mono-label">{t("settings.providers.savedProviders")}</p>
          <span className="registry-list__count">
            {t("settings.providers.savedCount", {
              count: formatNumber(group.providers.length),
            })}
          </span>
        </div>
        {group.providers.length === 0 ? (
          <p className="registry-empty">
            {t("settings.providers.noSavedRows")}
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
  const { t, formatNumber } = useI18n();
  return (
    <div className="registry-reindex">
      <div className="registry-reindex__copy">
        <p className="mono-label">{t("settings.reindex.eyebrow")}</p>
        <p className="registry-reindex__text">
          {t("settings.reindex.providerCopy")}
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
          {pending
            ? t("settings.reindex.reembedding")
            : t("settings.reindex.action")}
        </Button>
      </div>
      {result ? (
        <p className="reindex__result" role="status">
          <Icon name="check" size={14} />
          {t("settings.reindex.resultShort", {
            count: formatNumber(result.reindexed),
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
  const { t } = useI18n();
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
          eyebrow={t("settings.providers.deleteDialogEyebrow")}
          title={t("settings.providers.deleteDialogTitle")}
          description={t("settings.providers.deleteDialogDescription", {
            name:
              deleteTarget.label ||
              providerDisplayName(deleteTarget.provider),
            capability: capabilityLabel(deleteTarget.capability, t),
          })}
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
                {t("settings.common.cancel")}
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
                {deletePending
                  ? t("settings.providers.deleting")
                  : t("settings.providers.deleteProvider")}
              </Button>
            </>
          }
        >
          <p className="settings-lede">
            {deleteTarget.is_active
              ? t("settings.providers.deleteActiveNote")
              : t("settings.providers.deleteInactiveNote")}
          </p>
        </SettingsDialog>
      ) : null}

      {reindexOpen ? (
        <SettingsDialog
          eyebrow={t("settings.reindex.dialogEyebrow")}
          title={t("settings.reindex.dialogTitle")}
          description={t("settings.reindex.dialogDescription")}
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
                {t("settings.common.cancel")}
              </Button>
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={onConfirmReindex}
                disabled={reindexPending}
              >
                {reindexPending
                  ? t("settings.reindex.reembedding")
                  : t("settings.reindex.start")}
              </Button>
            </>
          }
        >
          <p className="settings-lede">{t("settings.reindex.dialogCopy")}</p>
        </SettingsDialog>
      ) : null}
    </>
  );
}

/** Four capability slots, their saved rows, and their encrypted key state. */
export function ProviderVaultPanel() {
  const { t, formatNumber } = useI18n();
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
        toast.success(t("settings.providers.addedToast"));
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
        toast.success(t("settings.providers.updatedToast"));
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
        toast.success(t("settings.providers.activatedToast"));
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
        toast.success(t("settings.providers.deactivatedToast"));
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
        toast.success(t("settings.providers.deletedToast"));
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
          t("settings.reindex.toast", {
            count: formatNumber(data.reindexed),
            model: data.model,
          }),
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
        aria-label={t("settings.providers.loadReadingAria")}
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
          <strong>{t("settings.providers.loadErrorTitle")}</strong>
          <p>{apiErrorMessage(registryQuery.error)}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void registryQuery.refetch()}
            disabled={registryQuery.isFetching}
          >
            <Icon name="ring" size={14} />
            {registryQuery.isFetching
              ? t("core.common.retrying")
              : t("core.common.retry")}
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
            {t("settings.providers.title")}
          </span>
        }
        action={
          <div className="settings-panel__badges">
            {registry?.reindex_required ? (
              <Badge tone="ochre" dot>
                {t("settings.providers.reindexRequired")}
              </Badge>
            ) : null}
            <Badge tone={registry?.vector_enabled ? "moss" : "neutral"} dot>
              {vectorBadgeLabel(
                registryQuery.isPending,
                registry?.vector_enabled,
                registryQuery.isError,
                t,
              )}
            </Badge>
          </div>
        }
        className="settings-panel"
      >
        <p className="settings-lede">{t("settings.providers.lede")}</p>

        {body}

        {registry?.reindex_required ? (
          <div className="settings-callout settings-callout--warn" role="status">
            <Icon name="history" size={18} />
            <div>
              <strong>{t("settings.providers.reindexRequired")}</strong>
              <p>{t("settings.providers.reindexRequiredBody")}</p>
            </div>
          </div>
        ) : null}

        <p className="settings-hint">{t("settings.providers.hint")}</p>
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
