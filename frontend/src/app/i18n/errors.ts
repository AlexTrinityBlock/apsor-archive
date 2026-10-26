import { useCallback } from "react";

import { ApiError } from "../../apis/fetch-client";
import { useI18n } from "./I18nProvider";
import type { TranslationKey } from "./locales";
import { getActiveLocale, translate, type Translate } from "./translate";

/**
 * Stable backend codes mapped to localized copy. Unknown codes fall back to
 * the server detail verbatim; provider/server text is never translated.
 */
const ERROR_CODE_KEYS = {
  invalid_request: "core.errors.invalid_request",
  unauthorized: "core.errors.unauthorized",
  authentication_required: "core.errors.unauthorized",
  invalid_credentials: "core.errors.invalid_credentials",
  account_disabled: "core.errors.account_disabled",
  password_change_required: "core.errors.password_change_required",
  current_password_invalid: "core.errors.current_password_invalid",
  account_not_found: "core.errors.account_not_found",
  username_taken: "core.errors.username_taken",
  cannot_disable_root: "core.errors.cannot_disable_root",
  last_root_protected: "core.errors.last_root_protected",
  setup_already_complete: "core.errors.setup_already_complete",
  invalid_username: "core.errors.invalid_username",
  invalid_profile: "core.errors.invalid_profile",
  weak_password: "core.errors.weak_password",
  password_mismatch: "core.errors.password_mismatch",
  login_throttled: "core.errors.login_throttled",
  storage_unavailable: "core.errors.storage_unavailable",
  agent_not_configured: "core.errors.agent_not_configured",
  agent_conversation_busy: "core.errors.agent_conversation_busy",
  agent_conversation_archived: "core.errors.agent_conversation_archived",
  agent_run_not_retryable: "core.errors.agent_run_not_retryable",
  agent_invalid_system_prompt: "core.errors.agent_invalid_system_prompt",
  agent_system_prompt_not_found: "core.errors.agent_system_prompt_not_found",
  file_content_unavailable: "core.errors.file_content_unavailable",
  setup_required: "core.errors.setup_required",
  login_failed: "core.errors.login_failed",
  rate_limited: "core.errors.rate_limited",
  not_found: "core.errors.not_found",
  internal_error: "core.errors.internal_error",
  network_error: "core.errors.network_error",
  forbidden: "core.errors.forbidden",
  conflict: "core.errors.conflict",
} as const satisfies Record<string, TranslationKey>;

const DEFAULT_FALLBACK_KEY: TranslationKey = "core.errors.generic";

/** Resolves a stable API error code to a translation key, when known. */
export function errorCodeKey(
  code: string | null | undefined,
): TranslationKey | null {
  if (!code) {
    return null;
  }
  const key = ERROR_CODE_KEYS[code as keyof typeof ERROR_CODE_KEYS];
  return key ?? null;
}

/**
 * Localizes a known backend error code, otherwise shows the server detail, then
 * a generic localized message. Raw server/provider copy is never translated.
 */
export function translateApiError(
  error: unknown,
  t: Translate,
  fallbackKey: TranslationKey = DEFAULT_FALLBACK_KEY,
): string {
  if (error instanceof ApiError) {
    const knownKey = errorCodeKey(error.code);
    if (knownKey !== null) {
      return t(knownKey);
    }
    if (error.detail.trim().length > 0) {
      return error.detail;
    }
    return t(fallbackKey);
  }
  return t(fallbackKey);
}

/** The same mapping for plain modules that cannot call React hooks. */
export function translateApiErrorWithActiveLocale(
  error: unknown,
  fallbackKey: TranslationKey = DEFAULT_FALLBACK_KEY,
): string {
  return translateApiError(
    error,
    (key, vars) => translate(getActiveLocale(), key, vars),
    fallbackKey,
  );
}

/** Hook form used by components: re-renders when the locale changes. */
export function useApiErrorMessage(): (
  error: unknown,
  fallbackKey?: TranslationKey,
) => string {
  const { t } = useI18n();
  return useCallback(
    (error: unknown, fallbackKey?: TranslationKey) =>
      translateApiError(error, t, fallbackKey),
    [t],
  );
}
