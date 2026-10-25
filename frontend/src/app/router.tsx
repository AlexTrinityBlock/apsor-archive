import { lazy, Suspense, useEffect } from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";
import { createBrowserRouter } from "react-router-dom";

import { AuthGate } from "./auth/AuthGate";
import {
  clearLastChatConversation,
  readLastChatConversation,
} from "./chat/session-storage";
import { AppShell } from "./component/AppShell";
import { RouteError } from "./component/RouteError";
import { RouteFallback } from "./component/RouteFallback";
import { NotFoundPage } from "./not-found/page";

const DashboardPage = lazy(() =>
  import("./home/page").then((module) => ({ default: module.DashboardPage })),
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
const MemoryPage = lazy(() =>
  import("./memory/page").then((module) => ({ default: module.MemoryPage })),
);
const ChatPage = lazy(() =>
  import("./chat/page").then((module) => ({ default: module.ChatPage })),
);
const QuestionsPage = lazy(() =>
  import("./questions/page").then((module) => ({ default: module.QuestionsPage })),
);
const AboutPage = lazy(() =>
  import("./about/page").then((module) => ({ default: module.AboutPage })),
);
const SettingsPage = lazy(() =>
  import("./settings/page").then((module) => ({ default: module.SettingsPage })),
);
const ProfilePage = lazy(() =>
  import("./profile/page").then((module) => ({ default: module.ProfilePage })),
);

/** Keeps the old query string when a removed workspace redirects to its home. */
function RedirectWithQuery({ to }: { readonly to: string }) {
  const location = useLocation();
  const [pathname, search = ""] = to.split("?");
  const params = new URLSearchParams(search);
  for (const [key, value] of new URLSearchParams(location.search)) {
    if (!params.has(key)) {
      params.set(key, value);
    }
  }
  const query = params.toString();
  return <Navigate to={query ? `${pathname}?${query}` : pathname} replace />;
}

/** Ask is no longer a workspace; Chat is the only inquiry surface. */
function AskRedirect() {
  return <Navigate to="/chat" replace />;
}

/** A draft arriving at `/chat` always starts a new conversation. */
function hasRouteDraft(state: unknown): boolean {
  if (typeof state !== "object" || state === null) {
    return false;
  }
  const draft = (state as { draft?: unknown }).draft;
  return typeof draft === "string" && draft.trim().length > 0;
}

/**
 * Resumes the last conversation, except when a route draft is pending.
 * The clear happens in an effect so render stays free of storage writes.
 */
function ChatEntry() {
  const location = useLocation();
  const draftPending = hasRouteDraft(location.state);

  useEffect(() => {
    if (draftPending) {
      clearLastChatConversation();
    }
  }, [draftPending]);

  if (!draftPending) {
    const saved = readLastChatConversation();
    if (saved !== null) {
      return <Navigate to={`/chat/${saved}`} replace />;
    }
  }

  return <ChatPage />;
}

function ViewerFileRedirect() {
  const { fileId } = useParams<{ fileId: string }>();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("tab", "files");
  if (fileId) {
    params.set("file", fileId);
  }
  return <Navigate to={`/library?${params.toString()}`} replace />;
}

function ViewerMemoryRedirect() {
  const { memoryId } = useParams<{ memoryId: string }>();
  return <Navigate to={`/memory/${memoryId ?? ""}`} replace />;
}

function ViewerMediaRedirect() {
  const { mediaId } = useParams<{ mediaId: string }>();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set("tab", "media");
  if (mediaId) {
    params.set("media", mediaId);
  }
  return <Navigate to={`/library?${params.toString()}`} replace />;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AuthGate />,
    errorElement: <RouteError />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/chat" replace /> },
          { path: "dashboard", element: <DashboardPage /> },
          { path: "overview", element: <Navigate to="/dashboard" replace /> },
          { path: "search", element: <SearchPage /> },
          { path: "timeline", element: <TimelinePage /> },
          { path: "library", element: <LibraryPage /> },
          { path: "tree", element: <Navigate to="/library" replace /> },
          { path: "media", element: <RedirectWithQuery to="/library?tab=media" /> },
          { path: "memory", element: <MemoryPage /> },
          { path: "memory/new", element: <MemoryPage /> },
          { path: "memory/:memoryId", element: <MemoryPage /> },
          { path: "chat", element: <ChatEntry /> },
          { path: "chat/:conversationId", element: <ChatPage /> },
          { path: "questions", element: <QuestionsPage /> },
          { path: "ask", element: <AskRedirect /> },
          { path: "about", element: <AboutPage /> },
          { path: "method", element: <Navigate to="/about" replace /> },
          { path: "docs", element: <Navigate to="/about" replace /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "profile", element: <ProfilePage /> },
          { path: "viewer/file/:fileId", element: <ViewerFileRedirect /> },
          { path: "viewer/media/:mediaId", element: <ViewerMediaRedirect /> },
          { path: "viewer/memory/:memoryId", element: <ViewerMemoryRedirect /> },
          {
            path: "*",
            element: (
              <Suspense fallback={<RouteFallback />}>
                <NotFoundPage />
              </Suspense>
            ),
          },
        ],
      },
    ],
  },
]);
