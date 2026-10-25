import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { getActiveLocale, translate } from "./app/i18n";
import { AppProviders } from "./app/providers";
import { router } from "./app/router";
import "./styles/index.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error(
    translate(getActiveLocale(), "core.boot.missingRoot"),
  );
}

createRoot(rootElement).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
