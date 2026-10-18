import { lazy } from "react";
import { createBrowserRouter } from "react-router-dom";

import { AuthGate } from "./auth/AuthGate";
import { AppShell } from "./component/AppShell";
import { NotFoundPage } from "./not-found/page";

const HomePage = lazy(() =>
  import("./home/page").then((module) => ({ default: module.HomePage })),
);
const SearchPage = lazy(() =>
  import("./search/page").then((module) => ({ default: module.SearchPage })),
);
const TimelinePage = lazy(() =>
  import("./timeline/page").then((module) => ({ default: module.TimelinePage })),
);
const LibraryPage = lazy(() =>
  import("./library/page").then((module) => ({ default: module.LibraryPage })),
);
const TreePage = lazy(() =>
  import("./tree/page").then((module) => ({ default: module.TreePage })),
);
const MediaPage = lazy(() =>
  import("./media/page").then((module) => ({ default: module.MediaPage })),
);
const MemoryPage = lazy(() =>
  import("./memory/page").then((module) => ({ default: module.MemoryPage })),
);
const AskPage = lazy(() =>
  import("./ask/page").then((module) => ({ default: module.AskPage })),
);
const MethodPage = lazy(() =>
  import("./method/page").then((module) => ({ default: module.MethodPage })),
);
const SettingsPage = lazy(() =>
  import("./settings/page").then((module) => ({ default: module.SettingsPage })),
);

/**
 * Each workspace loads on demand so the initial archive shell stays light.
 * View state that survives navigation continues to live in the query string.
 */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AuthGate />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <HomePage /> },
          { path: "search", element: <SearchPage /> },
          { path: "timeline", element: <TimelinePage /> },
          { path: "library", element: <LibraryPage /> },
          { path: "tree", element: <TreePage /> },
          { path: "media", element: <MediaPage /> },
          { path: "memory/:memoryId", element: <MemoryPage /> },
          { path: "ask", element: <AskPage /> },
          { path: "method", element: <MethodPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
