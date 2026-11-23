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

/**
 * Render slide one of a presentation into a small WebP data URL.
 *
 * The renderer package is imported on demand so the library route does not pay
 * for it until a deck actually approaches the viewport. The canvas follows the
 * deck's real aspect ratio when the package exposes it; CSS still contains the
 * result inside the 4:3 card stage.
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
  try {
    const { PPTXViewer } = await import("pptxviewjs");
    signal.throwIfAborted();

    viewer = new PPTXViewer({
      autoExposeGlobals: false,
      slideSizeMode: "fit",
      backgroundColor: "#ffffff",
    });
    await viewer.loadFile(buffer);
    signal.throwIfAborted();

    if (viewer.getSlideCount() <= 0) {
      throw new Error("The presentation has no slides");
    }

    const aspect = slideAspect(viewer);
    canvas = document.createElement("canvas");
    const canvasHeight = Math.max(1, Math.round(SLIDE_WIDTH * aspect));
    canvas.width = SLIDE_WIDTH;
    canvas.height = canvasHeight;
    // The renderer reads layout dimensions from the element. Keep the canvas
    // out of the flow but attached so those measurements are real.
    canvas.style.width = `${SLIDE_WIDTH}px`;
    canvas.style.height = `${canvasHeight}px`;
    canvas.style.position = "fixed";
    canvas.style.top = "0";
    canvas.style.left = "-10000px";
    canvas.style.pointerEvents = "none";
    document.body.appendChild(canvas);

    await viewer.render(canvas, { slideIndex: 0 });
    signal.throwIfAborted();

    const dataUrl = canvas.toDataURL("image/webp", SLIDE_QUALITY);
    return dataUrl.length > MAX_DATA_URL_LENGTH
      ? canvas.toDataURL("image/webp", 0.62)
      : dataUrl;
  } finally {
    viewer?.destroy();
    canvas?.remove();
  }
}
