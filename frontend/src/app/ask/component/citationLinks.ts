import type { CitationSchema } from "../../generated-apis-types/schemas";

/** The library reader destination for a cited file chunk. */
export function fileCitationHref(citation: CitationSchema): string | null {
  if (citation.file_id == null || citation.chunk == null) {
    return null;
  }
  const params = new URLSearchParams({
    file: String(citation.file_id),
    chunk: String(citation.chunk),
  });
  return `/library?${params.toString()}`;
}

/** The memory-trace destination for a cited memory. */
export function memoryCitationHref(citation: CitationSchema): string | null {
  if (citation.memory_id == null) {
    return null;
  }
  return `/memory/${citation.memory_id}`;
}

/** The DOM id of a summary citation card in the Sources rail. */
export function summarySourceId(citation: CitationSchema): string | null {
  if (citation.kind !== "summary" || citation.memory_summary_id == null) {
    return null;
  }
  return `ask-summary-source-${citation.memory_summary_id}`;
}
