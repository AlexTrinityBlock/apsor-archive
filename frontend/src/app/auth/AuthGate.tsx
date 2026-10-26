import { Outlet } from "react-router-dom";

import { Button } from "../component/Button";
import { Loader } from "../component/Loader";
import { TreeMark } from "../component/TreeMark";
import { TreeRings } from "../component/TreeRings";
import { useI18n } from "../i18n";
import { useAuth } from "./AuthProvider";
import { ChangePasswordScreen } from "./component/ChangePasswordScreen";
import { LoginScreen } from "./component/LoginScreen";
import { SetupScreen } from "./component/SetupScreen";
import "./auth.css";

function AuthLoading() {
  const { t } = useI18n();

  return (
    <main className="auth-loading" aria-busy="true">
      <div className="auth-loading__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>
      <span className="auth-loading__mark">
        <TreeMark size={34} />
      </span>
      <p className="eyebrow">{t("core.auth.loadingEyebrow")}</p>
      <Loader size={38} label={t("core.auth.loadingLabel")} />
      <p>{t("core.auth.opening")}</p>
    </main>
  );
}

function AuthLoadError({
  message,
  onRetry,
}: {
  readonly message: string;
  readonly onRetry: () => void;
}) {
  const { t } = useI18n();

  return (
    <main className="auth-loading auth-loading--error" role="alert">
      <div className="auth-loading__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>
      <span className="auth-loading__mark">
        <TreeMark size={32} />
      </span>
      <p className="eyebrow">{t("core.auth.loadErrorEyebrow")}</p>
      <h1>{t("core.auth.loadErrorTitle")}</h1>
      <p>{message}</p>
      <Button variant="primary" onClick={onRetry}>
        {t("core.auth.tryAgain")}
      </Button>
    </main>
  );
}

/**
 * The gate around every archive route. Setup is only possible before the first
 * root exists; an invalid cookie lands on sign-in, and a temporary-password
 * session cannot reach any content surface until it chooses a new password.
 */
export function AuthGate() {
  const {
    isLoading,
    loadError,
    retry,
    requiresSetup,
    isAuthenticated,
    mustChangePassword,
  } = useAuth();

  if (isLoading) {
    return <AuthLoading />;
  }
  if (loadError) {
    return <AuthLoadError message={loadError} onRetry={retry} />;
  }
  if (requiresSetup) {
    return <SetupScreen />;
  }
  if (!isAuthenticated) {
    return <LoginScreen />;
  }
  if (mustChangePassword) {
    return <ChangePasswordScreen />;
  }
  return <Outlet />;
}
