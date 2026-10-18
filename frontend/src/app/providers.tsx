import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ToastProvider } from "./component/Toast";
import { ThemeProvider } from "./hook/useTheme";
import { queryClient } from "./query-client";

/** App-wide providers, ordered so any descendant may use toasts and theme. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>{children}</ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
