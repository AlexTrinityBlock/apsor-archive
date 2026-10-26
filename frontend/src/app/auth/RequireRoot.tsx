import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "./AuthProvider";

/**
 * Root-only route guard. The backend independently returns 403 for non-root
 * callers, so this only keeps the hidden surface out of a normal user's way.
 */
export function RequireRoot({ children }: { readonly children: ReactNode }) {
  const { user, isImpersonating } = useAuth();

  if (user?.role !== "root") {
    // An impersonation target lands on Chat: the account switcher starts there
    // and /accounts is no longer a valid surface for this session. A normal
    // account still falls back to its own profile.
    return <Navigate to={isImpersonating ? "/chat" : "/profile"} replace />;
  }
  return <>{children}</>;
}
