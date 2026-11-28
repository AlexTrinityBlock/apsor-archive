import { useLocation } from "react-router-dom";

import { useGetFile } from "../../generated-apis-types/files/files";
import { parentPath } from "../../../lib/format";
import type { LibraryRoute } from "../../../lib/library-url";
import { normalizeLibraryPath } from "../component/library-utils";

/**
 * Resolve the shelf behind a preview.
 *
 * A direct `/library/files/:id` link has no folder in the path. The file
 * resource itself carries its current parent, so refresh-safe deep links still
 * render the correct shelf behind the preview. Navigation state is a faster
 * first paint when the user opened the file from a folder.
 */
export function usePreviewRoute(route: LibraryRoute) {
  const location = useLocation();
  const previewFileId = route.fileId;
  const previewFileQuery = useGetFile(previewFileId ?? 0, {
    query: { enabled: previewFileId !== null },
  });
  const routeState = location.state as
    | { readonly libraryFolderPath?: unknown }
    | null;
  const stateFolderPath =
    typeof routeState?.libraryFolderPath === "string"
      ? normalizeLibraryPath(routeState.libraryFolderPath)
      : null;

  let previewFolderPath: string | null = null;
  if (previewFileId !== null) {
    previewFolderPath = previewFileQuery.data
      ? parentPath(previewFileQuery.data.raw_file_path)
      : stateFolderPath ?? "/";
  }

  const path = route.folderPath ?? previewFolderPath ?? "/";
  const resolvingPath =
    previewFileId !== null &&
    route.folderPath === null &&
    !previewFileQuery.isSuccess &&
    !previewFileQuery.isError &&
    stateFolderPath === null;

  return { previewFileQuery, previewFolderPath, path, resolvingPath };
}
