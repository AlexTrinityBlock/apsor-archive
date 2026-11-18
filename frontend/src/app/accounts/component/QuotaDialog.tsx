import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import type {
  AccountQuotaSchema,
  AccountQuotaSchemaCategory,
  AccountSchema,
} from "../../generated-apis-types/schemas";
import type { TranslationKey } from "../../i18n";
import { useI18n } from "../../i18n";
import { AccountDialog } from "./AccountDialog";
import "../accounts.css";

type QuotaCategory = AccountQuotaSchemaCategory;

const CATEGORY_LABEL_KEYS = {
  chat: "core.accounts.quotaChat",
  embedding: "core.accounts.quotaEmbedding",
  web_search: "core.accounts.quotaWebSearch",
  web_fetch: "core.accounts.quotaWebFetch",
} as const satisfies Record<QuotaCategory, TranslationKey>;

const TOP_UP_MAX = 10 ** 12;

interface QuotaDialogProps {
  readonly account: AccountSchema;
  readonly onClose: () => void;
  readonly onSave: (
    category: QuotaCategory,
    enabled: boolean,
    granted: number | null,
  ) => void;
  readonly onTopUp: (category: QuotaCategory, amount: number) => void;
  readonly onReset: (category: QuotaCategory, granted: number | null) => void;
  readonly submitting: boolean;
  readonly error: string | null;
}

function parseGrant(raw: string): number | null | "invalid" {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return null;
  }
  if (!/^\d+$/.test(trimmed)) {
    return "invalid";
  }
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < 0 || value > TOP_UP_MAX) {
    return "invalid";
  }
  return value;
}

function parseAmount(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value <= 0 || value > TOP_UP_MAX) {
    return null;
  }
  return value;
}

function quotaSummary(
  quota: AccountQuotaSchema,
  formatNumber: (value: number) => string,
  unlimitedLabel: string,
): string {
  const granted =
    quota.granted === null ? unlimitedLabel : formatNumber(quota.granted);
  return `${formatNumber(quota.used)} / ${granted}`;
}

interface QuotaEditorProps {
  readonly quota: AccountQuotaSchema;
  readonly onSave: (
    category: QuotaCategory,
    enabled: boolean,
    granted: number | null,
  ) => void;
  readonly onTopUp: (category: QuotaCategory, amount: number) => void;
  readonly onReset: (category: QuotaCategory, granted: number | null) => void;
  readonly submitting: boolean;
  readonly error: string | null;
}

/**
 * Editor for one category. The parent remounts it with a key whenever the
 * persisted allowance changes, so the fields always start from server state
 * without an effect that copies props into state.
 */
function QuotaEditor({
  quota,
  onSave,
  onTopUp,
  onReset,
  submitting,
  error,
}: QuotaEditorProps) {
  const { t, formatNumber } = useI18n();
  const [enabled, setEnabled] = useState(quota.enabled);
  const [grantText, setGrantText] = useState(
    quota.granted === null ? "" : String(quota.granted),
  );
  const [amountText, setAmountText] = useState("");
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [localError, setLocalError] = useState<TranslationKey | null>(null);

  const unlimited = quota.granted === null;

  const save = () => {
    const grant = parseGrant(grantText);
    if (grant === "invalid") {
      setLocalError("core.accounts.quotaGrantInvalid");
      return;
    }
    setLocalError(null);
    onSave(quota.category, enabled, grant);
  };

  const topUp = () => {
    const amount = parseAmount(amountText);
    if (amount === null) {
      setLocalError("core.accounts.quotaTopUpInvalid");
      return;
    }
    setLocalError(null);
    onTopUp(quota.category, amount);
  };

  const reset = () => {
    const grant = parseGrant(grantText);
    if (grant === "invalid") {
      setLocalError("core.accounts.quotaGrantInvalid");
      return;
    }
    if (!confirmingReset) {
      setLocalError(null);
      setConfirmingReset(true);
      return;
    }
    setLocalError(null);
    onReset(quota.category, grant);
  };

  return (
    <div className="accounts-quota__editor">
      <dl className="accounts-quota__stats">
        <div>
          <dt>{t("core.accounts.quotaUsed")}</dt>
          <dd>{formatNumber(quota.used)}</dd>
        </div>
        <div>
          <dt>{t("core.accounts.quotaLifetime")}</dt>
          <dd>{formatNumber(quota.lifetime)}</dd>
        </div>
        <div>
          <dt>{t("core.accounts.quotaBeforeResetLabel")}</dt>
          <dd>{formatNumber(quota.used_before_reset)}</dd>
        </div>
        <div>
          <dt>{t("core.accounts.quotaRemaining")}</dt>
          <dd>
            {quota.remaining === null
              ? t("core.accounts.quotaUnlimited")
              : formatNumber(quota.remaining)}
          </dd>
        </div>
      </dl>

      <label className="accounts-quota__toggle">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
          disabled={submitting}
        />
        <span>
          <strong>{t("core.accounts.quotaEnabledLabel")}</strong>
          <small>{t("core.accounts.quotaEnabledHint")}</small>
        </span>
      </label>

      <div className="field">
        <label className="field-label" htmlFor="quota-grant">
          {t("core.accounts.quotaGrantLabel")}
        </label>
        <input
          id="quota-grant"
          className="input"
          type="text"
          inputMode="numeric"
          value={grantText}
          onChange={(event) => {
            setGrantText(event.target.value);
            setConfirmingReset(false);
          }}
          placeholder={t("core.accounts.quotaUnlimited")}
          disabled={submitting}
        />
        <small className="field-help">
          {t("core.accounts.quotaGrantHint")}
        </small>
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={save}
          disabled={submitting}
          className="accounts-quota__save"
        >
          {submitting
            ? t("core.accounts.quotaSaving")
            : t("core.accounts.quotaSave")}
        </Button>
      </div>

      <section
        className="accounts-quota__action"
        aria-label={t("core.accounts.quotaTopUpTitle")}
      >
        <div className="accounts-quota__action-copy">
          <strong>{t("core.accounts.quotaTopUpTitle")}</strong>
          <small>
            {unlimited
              ? t("core.accounts.quotaTopUpUnlimited")
              : t("core.accounts.quotaTopUpHint")}
          </small>
        </div>
        <div className="accounts-quota__action-row">
          <input
            className="input"
            type="text"
            inputMode="numeric"
            value={amountText}
            onChange={(event) => setAmountText(event.target.value)}
            placeholder="0"
            aria-label={t("core.accounts.quotaTopUpAmount")}
            disabled={submitting || unlimited}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={topUp}
            disabled={submitting || unlimited}
          >
            {t("core.accounts.quotaTopUp")}
          </Button>
        </div>
      </section>

      <section
        className="accounts-quota__action accounts-quota__action--danger"
        aria-label={t("core.accounts.quotaResetTitle")}
      >
        <div className="accounts-quota__action-copy">
          <strong>{t("core.accounts.quotaResetTitle")}</strong>
          <small>{t("core.accounts.quotaResetDescription")}</small>
        </div>
        {confirmingReset ? (
          <div className="accounts-quota__confirm" role="alert">
            <p>
              <Icon name="info" size={15} />
              {t("core.accounts.quotaResetConfirm", {
                used: formatNumber(quota.used),
              })}
            </p>
            <div className="accounts-quota__action-row">
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={reset}
                disabled={submitting}
              >
                {submitting
                  ? t("core.accounts.quotaResetting")
                  : t("core.accounts.quotaResetConfirmAction")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingReset(false)}
                disabled={submitting}
              >
                {t("core.accounts.quotaResetCancel")}
              </Button>
            </div>
          </div>
        ) : (
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={reset}
            disabled={submitting}
          >
            {t("core.accounts.quotaReset")}
          </Button>
        )}
      </section>

      {localError || error ? (
        <p className="accounts-form__error" role="alert">
          <Icon name="info" size={15} />
          {localError ? t(localError) : error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Per-category allowance editor for one account.
 *
 * A blank grant is unlimited; ``0`` is a real finite grant and is never
 * treated as blank. Top-up is available only for a finite grant. Reset always
 * asks for confirmation and preserves the lifetime counter in
 * ``used_before_reset``.
 */
export function QuotaDialog({
  account,
  onClose,
  onSave,
  onTopUp,
  onReset,
  submitting,
  error,
}: QuotaDialogProps) {
  const { t, formatNumber } = useI18n();
  const [active, setActive] = useState<QuotaCategory>("chat");
  const quota = account.quotas.find((item) => item.category === active);

  if (quota === undefined) {
    return null;
  }

  const name = account.display_name ?? account.username;
  const editorKey = [
    quota.category,
    quota.enabled ? "on" : "off",
    quota.granted ?? "unlimited",
    quota.lifetime,
    quota.used_before_reset,
  ].join(":");

  return (
    <AccountDialog
      eyebrow={t("core.accounts.eyebrow")}
      title={t("core.accounts.quotaDialogTitle")}
      description={t("core.accounts.quotaDialogDescription", { name })}
      onClose={onClose}
      busy={submitting}
      size="md"
      actions={
        <Button
          type="button"
          variant="ghost"
          onClick={onClose}
          disabled={submitting}
        >
          {t("core.accounts.quotaClose")}
        </Button>
      }
    >
      <p className="accounts-quota__hint">
        {t("core.accounts.quotaAccountingHint")}
      </p>
      <div className="accounts-quota">
        <div
          className="accounts-quota__tabs"
          role="tablist"
          aria-label={t("core.accounts.quotasTitle")}
        >
          {account.quotas.map((item) => (
            <button
              key={item.category}
              type="button"
              role="tab"
              aria-selected={item.category === active}
              className={[
                "accounts-quota__tab",
                item.category === active ? "is-active" : null,
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => setActive(item.category)}
              disabled={submitting}
              data-autofocus={item.category === "chat" ? true : undefined}
            >
              <span className="accounts-quota__tab-name">
                {t(CATEGORY_LABEL_KEYS[item.category])}
              </span>
              <span className="accounts-quota__tab-value">
                {quotaSummary(item, formatNumber, t("core.accounts.quotaUnlimited"))}
              </span>
              <Badge tone={item.enabled ? "moss" : "neutral"} dot>
                {item.enabled
                  ? t("core.accounts.quotaAllowed")
                  : t("core.accounts.quotaBlocked")}
              </Badge>
            </button>
          ))}
        </div>

        <QuotaEditor
          key={editorKey}
          quota={quota}
          onSave={onSave}
          onTopUp={onTopUp}
          onReset={onReset}
          submitting={submitting}
          error={error}
        />
      </div>
    </AccountDialog>
  );
}
