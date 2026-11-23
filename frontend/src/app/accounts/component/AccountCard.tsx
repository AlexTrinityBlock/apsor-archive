import type { ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import type {
  AccountQuotaSchema,
  AccountSchema,
  ModelAssignmentSchema,
} from "../../generated-apis-types/schemas";
import type { TranslationKey } from "../../i18n";
import { useI18n } from "../../i18n";
import type { AccountAction } from "./ConfirmAccountActionDialog";
import "../accounts.css";

interface AccountCardProps {
  readonly account: AccountSchema;
  readonly currentUserId: number | null;
  readonly assignment: ModelAssignmentSchema | null;
  readonly assignmentLoading: boolean;
  readonly assignmentError: boolean;
  readonly onAction: (action: AccountAction, account: AccountSchema) => void;
  readonly onManageQuotas: (account: AccountSchema) => void;
  readonly onManageModel: (account: AccountSchema) => void;
}

const QUOTA_LABEL_KEYS = {
  chat: "core.accounts.quotaChat",
  embedding: "core.accounts.quotaEmbedding",
  web_search: "core.accounts.quotaWebSearch",
  web_fetch: "core.accounts.quotaWebFetch",
} as const satisfies Record<string, TranslationKey>;

function initialsFor(name: string): string {
  return Array.from(name.trim()).slice(0, 2).join("").toUpperCase() || "?";
}

/**
 * One account information card: identity, state, dates, rolled-up agent usage,
 * and the safe root actions. The usage split is prompt vs completion only; the
 * cached count is a subset of prompt tokens and is not drawn in the bar.
 */
export function AccountCard({
  account,
  currentUserId,
  assignment,
  assignmentLoading,
  assignmentError,
  onAction,
  onManageQuotas,
  onManageModel,
}: AccountCardProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  const isCurrent = account.user_id === currentUserId;
  const isRoot = account.role === "root";
  const displayName = account.display_name ?? account.username;
  const usage = account.usage;
  const splitTotal = usage.prompt_tokens + usage.completion_tokens;
  const promptShare =
    splitTotal > 0 ? (usage.prompt_tokens / splitTotal) * 100 : 0;
  const completionShare = splitTotal > 0 ? 100 - promptShare : 0;
  const canImpersonate =
    !isRoot && !isCurrent && account.is_active && !account.must_change_password;

  return (
    <article
      className={["account-card", isCurrent ? "is-current" : null]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="account-card__head">
        <div className="account-card__identity">
          <span className="account-card__avatar" aria-hidden="true">
            {initialsFor(displayName)}
          </span>
          <div className="account-card__identity-copy">
            <h2 className="account-card__name">{displayName}</h2>
            <span className="account-card__username">
              @{account.username}
            </span>
          </div>
        </div>
        <div className="account-card__badges">
          <Badge tone={isRoot ? "ink" : "neutral"}>
            {isRoot ? t("core.accounts.roleRoot") : t("core.accounts.roleUser")}
          </Badge>
          <Badge tone={account.is_active ? "moss" : "neutral"} dot>
            {account.is_active
              ? t("core.accounts.active")
              : t("core.accounts.disabled")}
          </Badge>
          {account.must_change_password ? (
            <Badge tone="ochre">{t("core.accounts.mustChange")}</Badge>
          ) : null}
          {isCurrent ? (
            <Badge tone="moss">{t("core.accounts.currentAccount")}</Badge>
          ) : null}
        </div>
      </div>

      <dl className="account-card__meta">
        <div>
          <dt>{t("core.accounts.created")}</dt>
          <dd>
            <time dateTime={account.created_at}>
              {formatDateTime(account.created_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt>{t("core.accounts.lastLogin")}</dt>
          <dd>
            {account.last_login_at ? (
              <time dateTime={account.last_login_at}>
                {formatDateTime(account.last_login_at)}
              </time>
            ) : (
              t("core.accounts.never")
            )}
          </dd>
        </div>
      </dl>

      <section
        className="account-card__usage"
        aria-label={t("core.accounts.usageTitle")}
      >
        <div className="account-card__usage-head">
          <div className="account-card__total">
            <span className="account-card__usage-label">
              {t("core.accounts.totalTokens")}
            </span>
            <strong className="account-card__total-value">
              {formatNumber(usage.total_tokens)}
            </strong>
          </div>
          <dl className="account-card__usage-grid">
            <div>
              <dt>{t("core.accounts.promptTokens")}</dt>
              <dd>{formatNumber(usage.prompt_tokens)}</dd>
            </div>
            <div>
              <dt>{t("core.accounts.completionTokens")}</dt>
              <dd>{formatNumber(usage.completion_tokens)}</dd>
            </div>
            <div>
              <dt>{t("core.accounts.cachedTokens")}</dt>
              <dd>{formatNumber(usage.cached_tokens)}</dd>
            </div>
            <div>
              <dt>{t("core.accounts.apiCalls")}</dt>
              <dd>{formatNumber(usage.api_calls)}</dd>
            </div>
            <div>
              <dt>{t("core.accounts.turns")}</dt>
              <dd>{formatNumber(usage.turns)}</dd>
            </div>
          </dl>
        </div>

        <div
          className="account-card__split"
          role="img"
          aria-label={t("core.accounts.tokenSplitAria", {
            prompt: formatNumber(usage.prompt_tokens),
            completion: formatNumber(usage.completion_tokens),
          })}
        >
          <span
            className="account-card__split-prompt"
            style={{ width: `${promptShare}%` }}
          />
          <span
            className="account-card__split-completion"
            style={{ width: `${completionShare}%` }}
          />
        </div>
        <div className="account-card__split-legend" aria-hidden="true">
          <span>
            <i className="account-card__legend-prompt" />
            {t("core.accounts.promptTokens")}{" "}
            {formatNumber(usage.prompt_tokens)}
          </span>
          <span>
            <i className="account-card__legend-completion" />
            {t("core.accounts.completionTokens")}{" "}
            {formatNumber(usage.completion_tokens)}
          </span>
        </div>

        <p className="account-card__activity">
          <span className="account-card__activity-label">
            {t("core.accounts.lastActivity")}
          </span>
          {usage.last_activity_at ? (
            <time dateTime={usage.last_activity_at}>
              {formatDateTime(usage.last_activity_at)}
            </time>
          ) : (
            <span className="account-card__activity-empty">
              {t("core.accounts.noActivity")}
            </span>
          )}
        </p>
      </section>

      <section
        className="account-card__quotas"
        aria-label={t("core.accounts.quotasTitle")}
      >
        <div className="account-card__quotas-head">
          <h3 className="account-card__quotas-title">
            {t("core.accounts.quotasTitle")}
          </h3>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onManageQuotas(account)}
          >
            {t("core.accounts.quotasManage")}
          </Button>
        </div>
        <ul className="account-card__quota-list">
          {account.quotas.map((quota) => (
            <QuotaRow key={quota.category} quota={quota} />
          ))}
        </ul>
      </section>

      <AccountModelSection
        account={account}
        assignment={assignment}
        assignmentLoading={assignmentLoading}
        assignmentError={assignmentError}
        onManageModel={onManageModel}
      />

      {isCurrent || isRoot ? null : (
        <div className="account-card__actions">
          {canImpersonate ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onAction("impersonate", account)}
            >
              {t("core.accounts.impersonate")}
            </Button>
          ) : null}
          {account.is_active ? (
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={() => onAction("disable", account)}
            >
              {t("core.accounts.disable")}
            </Button>
          ) : (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onAction("enable", account)}
            >
              {t("core.accounts.enable")}
            </Button>
          )}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onAction("reset", account)}
          >
            {t("core.accounts.resetPassword")}
          </Button>
        </div>
      )}
    </article>
  );
}

interface AccountModelSectionProps {
  readonly account: AccountSchema;
  readonly assignment: ModelAssignmentSchema | null;
  readonly assignmentLoading: boolean;
  readonly assignmentError: boolean;
  readonly onManageModel: (account: AccountSchema) => void;
}

/** Compact model-assignment summary on one account card. */
function AccountModelSection({
  account,
  assignment,
  assignmentLoading,
  assignmentError,
  onManageModel,
}: AccountModelSectionProps) {
  const { t, formatNumber } = useI18n();
  let warningLabel: string | null = null;
  if (assignment !== null && assignment.warnings.length > 0) {
    warningLabel = t(
      assignment.warnings.length === 1
        ? "core.accounts.modelWarningCountOne"
        : "core.accounts.modelWarningCount",
      { count: formatNumber(assignment.warnings.length) },
    );
  }

  let content: ReactNode;
  if (assignment === null) {
    content = (
      <p className="account-card__model-empty">
        {assignmentLoading
          ? t("core.accounts.modelLoading")
          : t("core.accounts.modelUnavailable")}
      </p>
    );
  } else if (assignment.source === "unassigned") {
    content = (
      <div className="account-card__model-empty">
        <Badge tone="neutral" dot>
          {t("core.accounts.modelUnassigned")}
        </Badge>
      </div>
    );
  } else {
    const primaryParts = [assignment.effective_chat_model ?? "—"];
    if (assignment.effective_chat_effort) {
      primaryParts.push(assignment.effective_chat_effort);
    }
    if (assignment.effective_context_window_tokens !== null) {
      primaryParts.push(
        t("core.accounts.modelBudgetShort", {
          tokens: formatNumber(assignment.effective_context_window_tokens),
        }),
      );
    }
    if (assignment.effective_compaction_threshold_tokens !== null) {
      primaryParts.push(
        t("core.accounts.modelCompactionShort", {
          tokens: formatNumber(
            assignment.effective_compaction_threshold_tokens,
          ),
        }),
      );
    }
    const auxParts = [assignment.effective_aux_model ?? "—"];
    if (assignment.effective_aux_effort) {
      auxParts.push(assignment.effective_aux_effort);
    }
    content = (
      <dl className="account-card__model-grid">
        <div>
          <dt>{t("core.accounts.modelPrimary")}</dt>
          <dd>{primaryParts.join(" · ")}</dd>
        </div>
        <div>
          <dt>{t("core.accounts.modelAuxiliary")}</dt>
          <dd>{auxParts.join(" · ")}</dd>
        </div>
      </dl>
    );
  }

  return (
    <section
      className="account-card__model"
      aria-label={t("core.accounts.modelTitle")}
    >
      <div className="account-card__model-head">
        <h3 className="account-card__model-title">
          {t("core.accounts.modelTitle")}
        </h3>
        <div className="account-card__model-actions">
          {warningLabel ? <Badge tone="ochre">{warningLabel}</Badge> : null}
          {assignment?.degraded_reason ? (
            <Badge tone="ochre" dot>
              {t("core.accounts.modelDegradedBadge")}
            </Badge>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onManageModel(account)}
            disabled={assignment === null || assignmentLoading}
          >
            {t("core.accounts.modelManage")}
          </Button>
        </div>
      </div>
      {content}
      {assignmentError ? (
        <p className="account-card__model-empty">
          {t("core.accounts.modelUnavailable")}
        </p>
      ) : null}
    </section>
  );
}

interface QuotaRowProps {
  readonly quota: AccountQuotaSchema;
}

/** One allowance category: switch state, current/granted usage, and base. */
function QuotaRow({ quota }: QuotaRowProps) {
  const { t, formatNumber } = useI18n();
  const granted = quota.granted;
  const unlimited = granted === null;
  let percent = 0;
  if (granted !== null) {
    if (granted === 0) {
      percent = quota.used > 0 ? 100 : 0;
    } else {
      percent = Math.min(100, (quota.used / granted) * 100);
    }
  }
  const grantedLabel = unlimited
    ? t("core.accounts.quotaUnlimited")
    : formatNumber(granted);
  const label = t(QUOTA_LABEL_KEYS[quota.category]);

  return (
    <li className="account-card__quota">
      <div className="account-card__quota-head">
        <span className="account-card__quota-name">{label}</span>
        <Badge tone={quota.enabled ? "moss" : "neutral"} dot>
          {quota.enabled
            ? t("core.accounts.quotaAllowed")
            : t("core.accounts.quotaBlocked")}
        </Badge>
        <span className="account-card__quota-value">
          {formatNumber(quota.used)} / {grantedLabel}
        </span>
      </div>
      <div
        className="account-card__quota-track"
        role="img"
        aria-label={t("core.accounts.quotaUsageAria", {
          category: label,
          used: formatNumber(quota.used),
          granted: grantedLabel,
        })}
      >
        <span
          className={[
            "account-card__quota-fill",
            quota.enabled ? null : "is-blocked",
            unlimited ? "is-unlimited" : null,
          ]
            .filter(Boolean)
            .join(" ")}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="account-card__quota-base">
        {t("core.accounts.quotaBeforeReset", {
          value: formatNumber(quota.used_before_reset),
        })}
      </p>
    </li>
  );
}
