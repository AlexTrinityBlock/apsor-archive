import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "./AuthProvider";

/**
 * Root-only route guard. The backend independently returns 403 for non-root
 * callers, so this only keeps the hidden surface out of a normal user's way.
 */
export function RequireRoot({ children }: { readonly children: ReactNode }) {
  const { user } = useAuth();

  if (user?.role !== "root") {
    return <Navigate to="/profile" replace />;
  }
  return <>{children}</>;
}
