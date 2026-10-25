import type { Translate } from "./translate";

/**
 * Localizes the small set of service-state values the API exposes. Unknown
 * values are left verbatim rather than guessed.
 */
export function localizeStatus(
  t: Translate,
  value: string | null | undefined,
): string {
  switch (value) {
    case "ok":
      return t("core.status.ok");
    case "degraded":
      return t("core.status.degraded");
    case "error":
      return t("core.status.error");
    case "missing":
      return t("core.status.missing");
    case "configured":
      return t("core.status.configured");
    case "disabled":
      return t("core.status.disabled");
    case "unknown":
      return t("core.status.unknown");
    default:
      return value && value.trim().length > 0
        ? value
        : t("core.status.unknown");
  }
}
