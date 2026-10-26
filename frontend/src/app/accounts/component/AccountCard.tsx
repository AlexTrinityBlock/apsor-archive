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

/** One account row: identity, state badges, last sign-in, and safe actions. */
export function AccountCard({
  account,
  currentUserId,
  onAction,
}: AccountCardProps) {
  const { t, formatDateTime } = useI18n();
  const isCurrent = account.user_id === currentUserId;
  const isRoot = account.role === "root";
  const displayName = account.display_name ?? account.username;

  return (
    <article
      className={["account-card", isCurrent ? "is-current" : null]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="account-card__head">
        <div className="account-card__identity">
          <h2 className="account-card__name">{displayName}</h2>
          <span className="account-card__username">@{account.username}</span>
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

      {isCurrent || isRoot ? null : (
        <div className="account-card__actions">
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
