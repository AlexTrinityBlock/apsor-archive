import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useI18n } from "../i18n";
import { ChangePasswordForm } from "./component/ChangePasswordForm";
import "./auth.css";

/** Voluntary self-service password change inside the signed-in shell. */
export function ChangePasswordPage() {
  const { t } = useI18n();

  return (
    <div className="content-container content-container--form change-password-page">
      <PageHeader
        eyebrow={t("core.auth.changePassword.eyebrow")}
        title={t("core.auth.changePassword.title")}
        description={t("core.auth.changePassword.description")}
      />
      <Panel tone="plain" className="change-password-panel">
        <ChangePasswordForm />
      </Panel>
    </div>
  );
}
