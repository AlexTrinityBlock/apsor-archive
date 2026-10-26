import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import type { AccountSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { AccountDialog } from "./AccountDialog";
import "../accounts.css";

export type AccountAction = "disable" | "enable" | "reset";

interface ConfirmAccountActionDialogProps {
  readonly action: AccountAction;
  readonly account: AccountSchema;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
  readonly submitting: boolean;
  readonly error: string | null;
}

/** Confirmation for a disruptive account action, with the impact spelled out. */
export function ConfirmAccountActionDialog({
  action,
  account,
  onClose,
  onConfirm,
  submitting,
  error,
}: ConfirmAccountActionDialogProps) {
  const { t } = useI18n();

  let title = t("core.accounts.disable");
  let description = t("core.accounts.disableConfirm");
  let confirmLabel = t("core.accounts.disable");
  let confirmVariant: "primary" | "danger" = "danger";
  if (action === "enable") {
    title = t("core.accounts.enable");
    description = t("core.accounts.enableConfirm");
    confirmLabel = t("core.accounts.enable");
    confirmVariant = "primary";
  } else if (action === "reset") {
    title = t("core.accounts.resetTitle");
    description = t("core.accounts.resetDescription");
    confirmLabel = t("core.accounts.resetPassword");
  }

  return (
    <AccountDialog
      eyebrow={t("core.accounts.eyebrow")}
      title={title}
      description={description}
      onClose={onClose}
      busy={submitting}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={submitting}
            data-autofocus
          >
            {t("core.accounts.cancel")}
          </Button>
          <Button
            type="button"
            variant={confirmVariant}
            onClick={onConfirm}
            disabled={submitting}
          >
            {submitting ? t("core.accounts.working") : confirmLabel}
          </Button>
        </>
      }
    >
      <div className="accounts-confirm">
        <p className="accounts-confirm__identity">
          <strong>{account.display_name ?? account.username}</strong>
          <span>@{account.username}</span>
        </p>
        {error ? (
          <p className="accounts-form__error" role="alert">
            <Icon name="info" size={15} />
            {error}
          </p>
        ) : null}
      </div>
    </AccountDialog>
  );
}
