import { useQuery } from "@tanstack/react-query";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useChunkedText } from "../../viewer/component/useChunkedText";
import {
  ViewerResourceError,
  fetchViewerText,
  fileContentUrl,
} from "../../viewer/component/viewer-utils";

/** The content, state, and retry entry point the editor needs to load existing Markdown. */
export interface MarkdownDocumentState {
  /** Null while the content has not finished loading. */
  readonly content: string | null;
  readonly loading: boolean;
  readonly error: unknown;
  /** Whether the content was rebuilt from indexed chunks (no raw bytes exist). */
  readonly usingChunks: boolean;
  readonly retry: () => void;
}

function isMissingOriginal(error: unknown): boolean {
  return error instanceof ViewerResourceError && error.status === 404;
}

/**
 * Load the raw content of existing Markdown.
 *
 * When a stored original exists it is read directly from `/content`; if the file
 * only has indexed chunks (or the original is missing), it is rebuilt with the
 * viewer's `useChunkedText` so the two do not end up with separate error
 * handling.
 */
export function useMarkdownDocument(
  file: FileSchema | undefined,
): MarkdownDocumentState {
  const fileId = file?.id ?? 0;
  const totalChunks = file?.total_chunks ?? 0;
  const hasOriginal = file?.has_original ?? false;

  const originalQuery = useQuery({
    queryKey: ["library", "markdown-document", fileId],
    queryFn: ({ signal }) => fetchViewerText(fileContentUrl(fileId), signal),
    enabled: file !== undefined && hasOriginal,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });

  // Chunk reconstruction is enabled only when there is no original file; a 404 and
  // "there never was an original" take the same path.
  const fallbackToChunks = !hasOriginal || isMissingOriginal(originalQuery.error);
  const chunksQuery = useChunkedText(
    fileId,
    totalChunks,
    file !== undefined && fallbackToChunks,
  );

  const originalText = hasOriginal ? originalQuery.data : undefined;
  const chunkText = fallbackToChunks ? chunksQuery.data?.text : undefined;
  const content = originalText ?? chunkText ?? null;

  let error: unknown = null;
  if (originalQuery.error && !fallbackToChunks) {
    error = originalQuery.error;
  } else if (fallbackToChunks && chunksQuery.error) {
    error = chunksQuery.error;
  } else if (
    file !== undefined &&
    fallbackToChunks &&
    totalChunks === 0 &&
    !chunksQuery.isLoading
  ) {
    // No original and no chunks: report it unreadable explicitly so the editor
    // never stays stuck on loading.
    error = new ViewerResourceError(
      404,
      "file_content_unavailable",
      "",
    );
  }

  const loading =
    file !== undefined &&
    ((hasOriginal && originalQuery.isLoading) ||
      (fallbackToChunks && chunksQuery.isLoading));

  const retry = fallbackToChunks
    ? () => void chunksQuery.refetch()
    : () => void originalQuery.refetch();

  return {
    content,
    loading,
    error,
    usingChunks: fallbackToChunks && chunksQuery.data !== undefined,
    retry,
  };
}
