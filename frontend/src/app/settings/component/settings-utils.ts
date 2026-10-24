import { ApiError } from "../../../apis/fetch-client";
import type {
  AiProviderReadSchema,
  HealthSchema,
} from "../../generated-apis-types/schemas";
import type { BadgeTone } from "../../type/ui";

/** A status tone shared by dots, pills, and badges on the settings page. */
export type SettingsTone = "ok" | "degraded" | "error" | "unknown";

/** Returns a readable message for a rejected promise. */
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The archive could not complete that action.";
}

/** Prefers the API detail over the generic HTTP error message. */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail.trim().length > 0 ? error.detail : error.message;
  }
  return errorMessage(error);
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

/** Maps the provider config source onto a tone. */
export function sourceTone(source: AiProviderReadSchema["source"]): BadgeTone {
  if (source === "database") {
    return "moss";
  }
  if (source === "environment") {
    return "ochre";
  }
  return "neutral";
}

/** Human label for where the active provider configuration came from. */
export function sourceLabel(source: AiProviderReadSchema["source"]): string {
  if (source === "database") {
    return "Database";
  }
  if (source === "environment") {
    return "Environment";
  }
  return "Defaults";
}

/** Human label for the provider slot's runtime state. */
export function providerStateLabel(config: AiProviderReadSchema): string {
  if (!config.enabled) {
    return "Disabled";
  }
  return config.configured ? "Configured" : "Needs key";
}

/** Tone for the provider slot's runtime state. */
export function providerStateTone(config: AiProviderReadSchema): BadgeTone {
  if (!config.enabled) {
    return "neutral";
  }
  return config.configured ? "moss" : "ochre";
}

/** The API never returns a key, so this is a hint or an honest absence. */
export function providerKeyLabel(config: AiProviderReadSchema): string {
  if (config.provider === "none" || config.provider === "hashing") {
    return "No key required";
  }
  return config.key_hint ?? "No key stored";
}

/** Where the active key came from, without exposing it. */
export function providerKeySourceLabel(config: AiProviderReadSchema): string {
  if (config.provider === "none" || config.provider === "hashing") {
    return "Keyless provider";
  }
  if (config.key_source === "database") {
    return "Database key";
  }
  if (config.key_source === "environment") {
    return "Environment key";
  }
  return "No key";
}

/** Stable identity for a provider card so saved values reset the draft. */
export function providerCardKey(config: AiProviderReadSchema): string {
  return [
    config.purpose,
    config.source,
    config.provider,
    config.model,
    config.base_url ?? "",
    config.dimension ?? "",
    config.enabled ? "enabled" : "disabled",
    config.configured ? "configured" : "unconfigured",
    config.key_hint ?? "no-key",
    config.key_source,
    config.updated_at ?? "new",
  ].join("|");
}
