import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { useAuth } from "../AuthProvider";
import { AuthFrame } from "./AuthFrame";
import { ChangePasswordForm } from "./ChangePasswordForm";
import "../auth.css";

/**
 * Blocking full-screen password change for a temporary-password session. The
 * router keeps the current URL underneath, so the reader lands on the page
 * they originally requested once the flag clears.
 */
export function ChangePasswordScreen() {
  const { t } = useI18n();
  const { user, logout, isSubmitting } = useAuth();

  return (
    <AuthFrame
      eyebrow={t("core.auth.changePassword.eyebrow")}
      title={t("core.auth.changePassword.forcedTitle")}
      description={t("core.auth.changePassword.forcedDescription")}
      footer={
        <div className="auth-forced-footer">
          <p>{t("core.auth.changePassword.forcedFooter")}</p>
          <div className="auth-forced-footer__actions">
            {user ? (
              <span className="auth-forced-footer__account">
                {user.display_name ?? user.username}
              </span>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void logout()}
              disabled={isSubmitting}
            >
              <Icon name="logout" size={14} />
              {t("core.nav.signOut")}
            </Button>
          </div>
        </div>
      }
    >
      <ChangePasswordForm />
    </AuthFrame>
  );
}
