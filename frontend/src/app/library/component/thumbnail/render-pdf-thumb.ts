import { getDocument, type PDFPageProxy, type RenderTask } from "pdfjs-dist";

import { PDF_THUMB_OPTIONS } from "../../../viewer/pdfjs-config";
import { fileContentUrl } from "../../../viewer/component/viewer-utils";

// The card stage is at most a few hundred CSS pixels wide. A 480 px backdrop
// stays sharp on dense screens while keeping the WebP data URL small.
const PDF_THUMB_WIDTH = 480;
const PDF_THUMB_QUALITY = 0.85;
// Base64 inflates bytes by about a third; 160k characters is roughly 120 KB.
const MAX_DATA_URL_LENGTH = 160_000;

/**
 * Render page one of a PDF into a small WebP data URL.
 *
 * The document is loaded from its URL so PDF.js can use the API's byte-range
 * support. Aborting cancels the render and destroys the loading task; every
 * resource is released in `finally`, and no rejection escapes the caller.
 */
export async function renderPdfThumb(
  fileId: number,
  signal: AbortSignal,
): Promise<string> {
  signal.throwIfAborted();

  const loadingTask = getDocument({
    url: fileContentUrl(fileId),
    ...PDF_THUMB_OPTIONS,
  });
  let page: PDFPageProxy | null = null;
  let renderTask: RenderTask | null = null;

  const onAbort = () => {
    renderTask?.cancel();
    void loadingTask.destroy().catch(() => undefined);
  };
  signal.addEventListener("abort", onAbort, { once: true });

  try {
    const pdfDocument = await loadingTask.promise;
    signal.throwIfAborted();

    page = await pdfDocument.getPage(1);
    signal.throwIfAborted();

    const baseViewport = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({
      scale: PDF_THUMB_WIDTH / baseViewport.width,
    });
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(viewport.width));
    canvas.height = Math.max(1, Math.round(viewport.height));
    const context = canvas.getContext("2d");
    if (context === null) {
      throw new Error("Canvas 2D is unavailable");
    }

    renderTask = page.render({ canvas, viewport });
    await renderTask.promise;
    signal.throwIfAborted();

    const dataUrl = canvas.toDataURL("image/webp", PDF_THUMB_QUALITY);
    return dataUrl.length > MAX_DATA_URL_LENGTH
      ? canvas.toDataURL("image/webp", 0.62)
      : dataUrl;
  } finally {
    signal.removeEventListener("abort", onAbort);
    page?.cleanup();
    void loadingTask.destroy().catch(() => undefined);
  }
}
