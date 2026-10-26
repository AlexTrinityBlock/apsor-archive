import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import type { AccountSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { AccountDialog } from "./AccountDialog";
import "../accounts.css";

interface TemporaryPasswordDialogProps {
  readonly account: AccountSchema;
  readonly password: string;
  readonly onClose: () => void;
}

/**
 * One-time credential handoff. The password lives only in the parent page's
 * local dialog state and is dropped when this dialog closes or unmounts.
 */
export function TemporaryPasswordDialog({
  account,
  password,
  onClose,
}: TemporaryPasswordDialogProps) {
  const { t } = useI18n();

  return (
    <AccountDialog
      eyebrow={t("core.accounts.eyebrow")}
      title={t("core.accounts.temporaryPasswordTitle")}
      description={t("core.accounts.temporaryPasswordDescription")}
      onClose={onClose}
      actions={
        <Button type="button" variant="primary" onClick={onClose}>
          {t("core.accounts.done")}
        </Button>
      }
    >
      <div className="accounts-temp">
        <p className="accounts-temp__identity">
          <strong>{account.display_name ?? account.username}</strong>
          <span>@{account.username}</span>
        </p>

        <div className="field">
          <label
            className="field-label"
            htmlFor="temporary-password-value"
          >
            {t("core.accounts.temporaryPasswordLabel")}
          </label>
          <div className="accounts-temp__row">
            <input
              className="input accounts-temp__value"
              id="temporary-password-value"
              value={password}
              readOnly
              spellCheck={false}
              autoComplete="off"
              onFocus={(event) => event.currentTarget.select()}
              data-autofocus
            />
            <CopyButton
              value={password}
              label={t("core.accounts.copy")}
              className="accounts-temp__copy"
            />
          </div>
        </div>

        <p className="accounts-temp__warning">
          <Icon name="info" size={16} />
          <span>{t("core.accounts.temporaryPasswordWarning")}</span>
        </p>
      </div>
    </AccountDialog>
  );
}
