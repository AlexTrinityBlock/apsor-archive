import type { PPTXViewer as PptxViewerInstance } from "pptxviewjs";

import {
  fetchViewerBinary,
  fileContentUrl,
} from "../../../viewer/component/viewer-utils";

const SLIDE_WIDTH = 480;
const SLIDE_QUALITY = 0.85;
// Base64 inflates bytes by about a third; 160k characters is roughly 120 KB.
const MAX_DATA_URL_LENGTH = 160_000;
const DEFAULT_SLIDE_ASPECT = 9 / 16;
const THUMB_TIMEOUT_MS = 8_000;

/** Presentation size in EMU, read from the loaded package when available. */
interface SlideSize {
  readonly cx: number;
  readonly cy: number;
}

function slideAspect(viewer: PptxViewerInstance): number {
  const processor = (
    viewer as unknown as {
      processor?: { getSlideDimensions?: () => SlideSize };
    }
  ).processor;
  const size = processor?.getSlideDimensions?.();
  if (size && size.cx > 0 && size.cy > 0) {
    return size.cy / size.cx;
  }
  return DEFAULT_SLIDE_ASPECT;
}

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("Aborted", "AbortError");
}

/**
 * Settle with the render operation, or reject when it outlives the budget or
 * the caller aborts. The renderer cannot be cancelled, so the caller still
 * owns cleanup of the viewer and canvas.
 */
function settleWithin<T>(
  operation: Promise<T>,
  signal: AbortSignal,
  timeoutMs: number,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    let timer: number | undefined;

    function cleanup(): void {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      signal.removeEventListener("abort", onAbort);
    }

    function settle(action: () => void): void {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      action();
    }

    function fail(reason: unknown): void {
      settle(() => reject(reason));
    }

    function onAbort(): void {
      fail(abortReason(signal));
    }

    timer = window.setTimeout(() => {
      fail(new Error("Presentation thumbnail timed out"));
    }, timeoutMs);
    signal.addEventListener("abort", onAbort, { once: true });

    operation.then(
      (value) => settle(() => resolve(value)),
      (error: unknown) => fail(error),
    );

    if (signal.aborted) {
      fail(abortReason(signal));
    }
  });
}

/**
 * Release a thumbnail renderer and its staging canvas. Cleanup failures are
 * swallowed so they cannot mask the render result or the original error.
 */
function disposeThumb(
  viewer: PptxViewerInstance | null,
  canvas: HTMLCanvasElement | null,
): void {
  try {
    viewer?.destroy();
  } catch {
    // The renderer is already unusable; the canvas still has to go.
  }
  canvas?.remove();
}

/**
 * Render slide one of a presentation into a small WebP data URL.
 *
 * The renderer package is imported on demand so the library route does not pay
 * for it until a deck actually approaches the viewport. The canvas follows the
 * deck's real aspect ratio when the package exposes it; CSS still contains the
 * result inside the 4:3 card stage. Load and render share one bounded budget so
 * a malformed deck settles the thumbnail instead of hanging the queue.
 */
export async function renderPptxThumb(
  fileId: number,
  signal: AbortSignal,
): Promise<string> {
  signal.throwIfAborted();

  const buffer = await fetchViewerBinary(fileContentUrl(fileId), signal);
  signal.throwIfAborted();

  let viewer: PptxViewerInstance | null = null;
  let canvas: HTMLCanvasElement | null = null;

  const render = async (): Promise<string> => {
    const { PPTXViewer } = await import("pptxviewjs");
    signal.throwIfAborted();

    const instance = new PPTXViewer({
      autoExposeGlobals: false,
      // The default delayed chart re-render would fire after this function has
      // destroyed the viewer, raising "No PPTX loaded. Call loadFile() first."
      autoChartRerenderDelayMs: 0,
      slideSizeMode: "fit",
      backgroundColor: "#ffffff",
    });
    viewer = instance;
    await instance.loadFile(buffer);
    signal.throwIfAborted();

    if (instance.getSlideCount() <= 0) {
      throw new Error("The presentation has no slides");
    }

    const aspect = slideAspect(instance);
    const element = document.createElement("canvas");
    canvas = element;
    const canvasHeight = Math.max(1, Math.round(SLIDE_WIDTH * aspect));
    element.width = SLIDE_WIDTH;
    element.height = canvasHeight;
    // The renderer reads layout dimensions from the element. Keep the canvas
    // out of the flow but attached so those measurements are real.
    element.style.width = `${SLIDE_WIDTH}px`;
    element.style.height = `${canvasHeight}px`;
    element.style.position = "fixed";
    element.style.top = "0";
    element.style.left = "-10000px";
    element.style.pointerEvents = "none";
    document.body.appendChild(element);

    await instance.render(element, { slideIndex: 0 });
    signal.throwIfAborted();

    const dataUrl = element.toDataURL("image/webp", SLIDE_QUALITY);
    return dataUrl.length > MAX_DATA_URL_LENGTH
      ? element.toDataURL("image/webp", 0.62)
      : dataUrl;
  };

  try {
    return await settleWithin(render(), signal, THUMB_TIMEOUT_MS);
  } finally {
    disposeThumb(viewer, canvas);
  }
}
