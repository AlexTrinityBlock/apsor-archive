import { lazy, Suspense } from "react";
import { useParams } from "react-router-dom";

import "./viewer.css";

import { ViewerMissing, ViewerRouteFallback } from "./component/ViewerStates";
import { ViewerShell } from "./component/ViewerShell";
import { parseViewerId } from "./component/viewer-utils";

const FileViewer = lazy(() =>
  import("./component/FileViewer").then((module) => ({ default: module.FileViewer })),
);
const MediaViewer = lazy(() =>
  import("./component/MediaViewer").then((module) => ({ default: module.MediaViewer })),
);
const MemoryViewer = lazy(() =>
  import("./component/MemoryViewer").then((module) => ({ default: module.MemoryViewer })),
);

function InvalidViewer({ routeId }: { readonly routeId: string }) {
  return (
    <ViewerShell kind="Viewer" title="Invalid resource link" backTo="/" backLabel="Archive">
      <ViewerMissing
        title="This viewer link is not a valid archive id."
        message={`“${routeId}” is not a positive integer resource id. Use a link from a citation, file card, or media sheet.`}
        backTo="/"
        backLabel="Back to the archive"
      />
    </ViewerShell>
  );
}

/**
 * Dedicated resource viewer for `/viewer/file/:fileId`,
 * `/viewer/media/:mediaId`, and `/viewer/memory/:memoryId`.
 *
 * The route sits under `AuthGate` as a sibling of `AppShell`, so the viewer
 * owns its own full-screen chrome, top bar, and Suspense boundary. Each
 * resource engine is split into its own lazy chunk.
 */
export function ViewerPage() {
  const { fileId, mediaId, memoryId } = useParams<{
    fileId?: string;
    mediaId?: string;
    memoryId?: string;
  }>();

  if (fileId !== undefined) {
    const parsed = parseViewerId(fileId);
    return (
      <Suspense fallback={<ViewerRouteFallback />}>
        {parsed === null ? <InvalidViewer routeId={fileId} /> : <FileViewer fileId={parsed} />}
      </Suspense>
    );
  }

  if (mediaId !== undefined) {
    const parsed = parseViewerId(mediaId);
    return (
      <Suspense fallback={<ViewerRouteFallback />}>
        {parsed === null ? <InvalidViewer routeId={mediaId} /> : <MediaViewer mediaId={parsed} />}
      </Suspense>
    );
  }

  if (memoryId !== undefined) {
    const parsed = parseViewerId(memoryId);
    return (
      <Suspense fallback={<ViewerRouteFallback />}>
        {parsed === null ? (
          <InvalidViewer routeId={memoryId} />
        ) : (
          <MemoryViewer memoryId={parsed} />
        )}
      </Suspense>
    );
  }

  return (
    <ViewerShell kind="Viewer" title="No resource addressed" backTo="/" backLabel="Archive">
      <ViewerMissing
        title="No resource was addressed."
        message="Open a viewer link from a citation, a file card, or the media gallery."
        backTo="/"
        backLabel="Back to the archive"
      />
    </ViewerShell>
  );
}
