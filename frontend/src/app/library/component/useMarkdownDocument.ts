import { useQuery } from "@tanstack/react-query";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useChunkedText } from "../../viewer/component/useChunkedText";
import {
  ViewerResourceError,
  fetchViewerText,
  fileContentUrl,
} from "../../viewer/component/viewer-utils";

/** 編輯器載入既有 Markdown 時需要的內容、狀態與重試入口。 */
export interface MarkdownDocumentState {
  /** 內容尚未載入完成時為 null。 */
  readonly content: string | null;
  readonly loading: boolean;
  readonly error: unknown;
  /** 內容是否由已索引分段重建（原始位元組不存在）。 */
  readonly usingChunks: boolean;
  readonly retry: () => void;
}

function isMissingOriginal(error: unknown): boolean {
  return error instanceof ViewerResourceError && error.status === 404;
}

/**
 * 載入既有 Markdown 的原始內容。
 *
 * 有儲存原始檔時直接讀取 `/content`；若該檔案只有索引分段（或原始檔已
 * 遺失），則沿用 viewer 的 `useChunkedText` 重建，避免兩套錯誤處理分歧。
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

  // 原始檔不存在時才啟用分段重建；404 與「本來就沒有原始檔」走同一條路。
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
    // 沒有原始檔也沒有分段：明確回報不可讀，避免編輯器永遠停在載入中。
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
