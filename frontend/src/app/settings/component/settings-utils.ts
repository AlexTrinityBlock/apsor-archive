import {
  getActiveLocale,
  translate,
  type TranslationKey,
} from "../../i18n";
import { translateApiErrorWithActiveLocale } from "../../i18n/errors";
import type {
  HealthSchema,
  ProviderReadSchema,
} from "../../generated-apis-types/schemas";
import type { BadgeTone } from "../../type/ui";

/** A status tone shared by dots, pills, and badges on the settings page. */
export type SettingsTone = "ok" | "degraded" | "error" | "unknown";

/** Human labels for provider kinds, falling back to the raw API value. */
const PROVIDER_LABELS: Readonly<Record<string, string>> = {
  deepseek: "DeepSeek",
  "openai-compatible": "OpenAI-compatible",
  openai: "OpenAI",
  tavily: "Tavily",
};

function settingsLabel(key: TranslationKey): string {
  return translate(getActiveLocale(), key);
}

/**
 * Returns a localized message for a rejected promise. Known backend codes are
 * translated; unknown server detail is shown verbatim; otherwise the generic
 * localized message is returned.
 */
export function errorMessage(error: unknown): string {
  return translateApiErrorWithActiveLocale(error);
}

/** Same mapping, kept as the shared name used by Settings call sites. */
export function apiErrorMessage(error: unknown): string {
  return translateApiErrorWithActiveLocale(error);
}

/** Maps a status tone onto the shared badge palette. */
export function toneToBadge(tone: SettingsTone): BadgeTone {
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

/** Reads a health-style status string, which is ok/degraded/error style. */
export function serviceTone(value: string | undefined): SettingsTone {
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

/** Compresses the three health checks into one overall tone. */
export function systemTone(
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

/** A readable provider name without exposing any key material. */
export function providerDisplayName(provider: string): string {
  if (provider === "hashing") {
    return settingsLabel("settings.utils.providerHashing");
  }
  if (provider === "none") {
    return settingsLabel("settings.utils.providerNone");
  }
  return PROVIDER_LABELS[provider] ?? provider;
}

/** Maps the provider config source onto a tone. */
export function sourceTone(source: ProviderReadSchema["source"]): BadgeTone {
  if (source === "database") {
    return "moss";
  }
  if (source === "environment") {
    return "ochre";
  }
  return "neutral";
}

/** Human label for where the active provider configuration came from. */
export function sourceLabel(source: ProviderReadSchema["source"]): string {
  if (source === "database") {
    return settingsLabel("settings.utils.sourceDatabase");
  }
  if (source === "environment") {
    return settingsLabel("settings.utils.sourceEnvironment");
  }
  return settingsLabel("settings.utils.sourceDefaults");
}

/** Whether the provider stores a usable key already. */
export function isProviderKeyless(
  config: ProviderReadSchema,
  keylessProviders: readonly string[],
): boolean {
  return keylessProviders.includes(config.provider);
}

/** The configured state of one provider row. */
export function providerConfiguredLabel(config: ProviderReadSchema): string {
  if (config.provider === "none") {
    return settingsLabel("settings.utils.disabled");
  }
  return config.configured
    ? settingsLabel("settings.utils.configured")
    : settingsLabel("settings.utils.needsKey");
}

/** Tone for a provider row's configured state. */
export function providerConfiguredTone(
  config: ProviderReadSchema,
): BadgeTone {
  if (config.provider === "none") {
    return "neutral";
  }
  return config.configured ? "moss" : "ochre";
}

/** Human label for a saved provider's active state. */
export function providerStateLabel(config: ProviderReadSchema): string {
  if (!config.is_active) {
    return settingsLabel("settings.utils.inactive");
  }
  return providerConfiguredLabel(config);
}

/** Tone for a saved provider's active state. */
export function providerStateTone(config: ProviderReadSchema): BadgeTone {
  if (!config.is_active) {
    return "neutral";
  }
  return providerConfiguredTone(config);
}

/** The API never returns a key, so this is a hint or an honest absence. */
export function providerKeyLabel(
  config: ProviderReadSchema,
  keyless = false,
): string {
  if (keyless || config.provider === "none") {
    return settingsLabel("settings.utils.noKeyRequired");
  }
  return config.key_hint ?? settingsLabel("settings.utils.noKeyStored");
}

/** Where the active key came from, without exposing it. */
export function providerKeySourceLabel(
  config: ProviderReadSchema,
  keyless = false,
): string {
  if (keyless || config.provider === "none") {
    return settingsLabel("settings.utils.keylessProvider");
  }
  if (config.key_source === "database") {
    return settingsLabel("settings.utils.databaseKey");
  }
  if (config.key_source === "environment") {
    return settingsLabel("settings.utils.environmentKey");
  }
  return settingsLabel("settings.utils.noKey");
}

/** Maps a key source onto the shared badge palette. */
export function keySourceTone(
  config: ProviderReadSchema,
  keyless = false,
): BadgeTone {
  if (keyless || config.provider === "none") {
    return "neutral";
  }
  if (config.key_source === "database") {
    return "moss";
  }
  if (config.key_source === "environment") {
    return "ochre";
  }
  return "neutral";
}

/** A provider row's model, base URL, and dimension for compact summaries. */
export function providerEndpointSummary(
  config: ProviderReadSchema,
  supportsModel: boolean,
  supportsDimension: boolean,
): readonly string[] {
  const parts: string[] = [providerDisplayName(config.provider)];
  if (supportsModel && config.model) {
    parts.push(config.model);
  }
  if (config.base_url) {
    parts.push(config.base_url);
  }
  if (supportsDimension) {
    parts.push(config.dimension === null ? "default dimension" : `${config.dimension}-D`);
  }
  return parts;
}

/** Stable identity for a provider card so saved values reset the draft. */
export function providerCardKey(config: ProviderReadSchema): string {
  return [
    config.capability,
    config.id ?? "virtual",
    config.source,
    config.provider,
    config.model ?? "",
    config.base_url ?? "",
    config.dimension ?? "",
    config.is_active ? "active" : "inactive",
    config.configured ? "configured" : "unconfigured",
    config.key_hint ?? "no-key",
    config.key_source,
    config.updated_at ?? "new",
  ].join("|");
}

/** Stable identity for a registry row inside one capability group. */
export function providerRegistryCardKey(
  capability: ProviderReadSchema["capability"],
  config: ProviderReadSchema,
): string {
  return `${capability}:${providerCardKey(config)}`;
}
