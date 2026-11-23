/**
 * Shared PDF.js worker setup and first-page thumbnail options.
 *
 * The chat bubble and the library thumbnail renderer both read a PDF over
 * HTTP range requests and only draw page one. Keeping the options here means
 * both surfaces disable full streaming and automatic prefetch in the same
 * place, while the viewer's full document options stay independent.
 */
import { GlobalWorkerOptions, type getDocument } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?worker&url";

GlobalWorkerOptions.workerSrc = workerUrl;

type PdfDocumentOptions = NonNullable<Parameters<typeof getDocument>[0]>;

// Range loading keeps the request small for large PDFs. Both streaming layers
// are disabled because a thumbnail never reads past the first page. PDF.js 6
// no longer exposes the eval flag in its public type and has dropped runtime
// eval; keep the flag pinned defensively without widening every other option.
export const PDF_THUMB_OPTIONS = {
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
  isEvalSupported: false,
  withCredentials: true,
  rangeChunkSize: 256 * 1024,
  disableStream: true,
  disableAutoFetch: true,
} as unknown as PdfDocumentOptions;
