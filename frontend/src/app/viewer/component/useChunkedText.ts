/**
 * Rebuild a text-only record from its indexed chunks.
 *
 * The read_file API returns one window at a time. Hooks cannot vary in number,
 * so one query walks the windows sequentially with the generated `readFile`
 * function, deduplicates chunk indexes, and trims the overlap between entries.
 */
import { useQuery } from "@tanstack/react-query";

import { readFile } from "../../generated-apis-types/files/files";
import { joinChunkContents, ViewerResourceError } from "./viewer-utils";

interface ChunkedText {
  readonly text: string;
  readonly chunkCount: number;
}

/** Fetch every chunk window for a file and merge them into one text body. */
export function useChunkedText(
  fileId: number,
  totalChunks: number,
  enabled: boolean,
) {
  return useQuery<ChunkedText>({
    queryKey: ["viewer", "file-chunks", fileId, totalChunks],
    enabled: enabled && totalChunks > 0,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: async ({ signal }) => {
      const collected = new Map<number, string>();
      let cursor = 1;
      const guardLimit = Math.ceil(totalChunks / 11) + 3;

      for (let pass = 0; pass < guardLimit && cursor <= totalChunks; pass += 1) {
        const center = Math.min(cursor + 5, totalChunks);
        const window = await readFile(fileId, center, { chunk_range: 5 }, { signal });
        for (const chunk of window.chunks) {
          collected.set(chunk.chunk, chunk.content);
        }
        if (window.chunk_end < cursor) {
          break;
        }
        cursor = window.chunk_end + 1;
      }

      const chunks = [...collected.entries()]
        .sort(([left], [right]) => left - right)
        .map(([chunk, content]) => ({ chunk, content }));
      if (chunks.length === 0) {
        throw new ViewerResourceError(
          404,
          "file_content_unavailable",
          "This record has no stored original and no indexed chunks.",
        );
      }
      return { text: joinChunkContents(chunks), chunkCount: chunks.length };
    },
  });
}
