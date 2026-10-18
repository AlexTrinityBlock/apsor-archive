import { Outlet } from "react-router-dom";

import { Button } from "../component/Button";
import { Loader } from "../component/Loader";
import { TreeMark } from "../component/TreeMark";
import { TreeRings } from "../component/TreeRings";
import { useAuth } from "./AuthProvider";
import { LoginScreen } from "./component/LoginScreen";
import { SetupScreen } from "./component/SetupScreen";
import "./auth.css";

function AuthLoading() {
  return (
    <main className="auth-loading">
      <div className="auth-loading__rings" aria-hidden="true">
        <TreeRings variant="cta" />
      </div>
      <TreeMark size={54} />
      <p className="eyebrow">DendroMatrix · local archive</p>
      <Loader size={42} label="Checking the keeper session" />
      <p>Opening the rings…</p>
    </main>
  );
}

function AuthLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="auth-loading auth-loading--error">
      <TreeMark size={54} />
      <p className="eyebrow">The archive did not answer</p>
      <h1>We could not check the session.</h1>
      <p>{message}</p>
      <Button variant="ink" onClick={onRetry}>
        Try again
      </Button>
    </main>
  );
}

/**
 * The gate around every archive route. Setup is only possible before the owner
 * exists; otherwise an invalid or expired cookie lands on the login screen.
 */
export function AuthGate() {
  const {
    isLoading,
    loadError,
    retry,
    requiresSetup,
    isAuthenticated,
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
  return <Outlet />;
}
