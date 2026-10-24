import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { AuthProvider } from "./auth/AuthProvider";
import { ToastProvider } from "./component/Toast";
import { queryClient } from "./query-client";

/** App-wide providers, ordered so any descendant may use toasts and auth. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
