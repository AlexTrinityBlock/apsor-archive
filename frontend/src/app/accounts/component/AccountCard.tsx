import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import type { AccountSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import type { AccountAction } from "./ConfirmAccountActionDialog";
import "../accounts.css";

interface AccountCardProps {
  readonly account: AccountSchema;
  readonly currentUserId: number | null;
  readonly onAction: (action: AccountAction, account: AccountSchema) => void;
}

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
  onAction,
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
