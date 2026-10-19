import { lazy, Suspense } from "react";
import { createBrowserRouter } from "react-router-dom";

import { AuthGate } from "./auth/AuthGate";
import { AppShell } from "./component/AppShell";
import { RouteFallback } from "./component/RouteFallback";
import { NotFoundPage } from "./not-found/page";
import { loadViewerPage } from "./viewer/route";

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
const ChatPage = lazy(() =>
  import("./chat/page").then((module) => ({ default: module.ChatPage })),
);
const QuestionsPage = lazy(() =>
  import("./questions/page").then((module) => ({ default: module.QuestionsPage })),
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
const ViewerPage = lazy(loadViewerPage);

function ViewerRoute() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <ViewerPage />
    </Suspense>
  );
}

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
          { path: "chat", element: <ChatPage /> },
          { path: "chat/:conversationId", element: <ChatPage /> },
          { path: "questions", element: <QuestionsPage /> },
          { path: "ask", element: <AskPage /> },
          { path: "method", element: <MethodPage /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
      { path: "viewer/file/:fileId", element: <ViewerRoute /> },
      { path: "viewer/media/:mediaId", element: <ViewerRoute /> },
      { path: "viewer/memory/:memoryId", element: <ViewerRoute /> },
    ],
  },
]);
