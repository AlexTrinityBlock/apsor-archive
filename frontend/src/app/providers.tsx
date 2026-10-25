import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { AuthProvider } from "./auth/AuthProvider";
import { ToastProvider } from "./component/Toast";
import { I18nProvider } from "./i18n";
import { queryClient } from "./query-client";

/**
 * App-wide providers. I18n is outermost so auth, setup, route errors, and
 * toasts all share the same locale; the rest of the order is unchanged.
 */
export function AppProviders({ children }: { readonly children: ReactNode }) {
  return (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AuthProvider>{children}</AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}
