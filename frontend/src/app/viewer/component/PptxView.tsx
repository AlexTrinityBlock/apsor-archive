import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import type { PPTXViewer as PptxViewerInstance } from "pptxviewjs";

import { Button } from "../../component/Button";
import { useI18n } from "../../i18n";
import { ChunkFallback } from "./ChunkFallback";
import { ViewerErrorState, ViewerLoading } from "./ViewerStates";
import { fetchViewerBinary, fileDownloadUrl } from "./viewer-utils";
import { useElementWidth } from "./useElementWidth";

interface PptxViewProps {
  readonly fileId: number;
  readonly fileUrl: string;
  readonly fileName: string;
  readonly totalChunks: number;
}

/** Presentation size in EMU, read from the loaded package when available. */
interface SlideSize {
  readonly cx: number;
  readonly cy: number;
}

const DEFAULT_SLIDE_ASPECT = 9 / 16;

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

/** A one-line reason from an unknown error, or null when there was no error. */
function errorReason(error: unknown): string {
  return error instanceof Error ? error.message.trim() : "";
}

/**
 * PPTX preview with a canvas renderer and slide-by-slide navigation.
 *
 * The renderer is imported lazily so the initial bundle stays small, and the
 * original bytes are fetched through the shared viewer loader. Every async
 * continuation is guarded by a cancelled flag because a slide render can finish
 * after the viewer unmounts or the deck is replaced. If loading or rendering
 * fails, the indexed chunks remain readable through `ChunkFallback`.
 */
export function PptxView({ fileId, fileUrl, fileName, totalChunks }: PptxViewProps) {
  const { t, formatNumber } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewerRef = useRef<PptxViewerInstance | null>(null);
  const [setContainerElement, containerWidth] = useElementWidth<HTMLDivElement>();
  const [deckReady, setDeckReady] = useState(false);
  const [slideCount, setSlideCount] = useState(0);
  const [slideIndex, setSlideIndex] = useState(0);
  const [rendering, setRendering] = useState(false);
  const [hasRendered, setHasRendered] = useState(false);
  const [failureReason, setFailureReason] = useState<string | null>(null);

  const binaryQuery = useQuery({
    queryKey: ["viewer", "file-binary", fileId],
    queryFn: ({ signal }) => fetchViewerBinary(fileUrl, signal),
    retry: false,
    staleTime: 5 * 60_000,
  });

  const data = binaryQuery.data;

  // Load the deck once per fetched original. The viewer instance and the
  // cancelled flag are local to this effect, so a replaced deck never shares a
  // renderer with the previous one.
  useEffect(() => {
    if (!data) {
      return;
    }
    let cancelled = false;
    let viewer: PptxViewerInstance | null = null;

    void import("pptxviewjs")
      .then(async ({ PPTXViewer }) => {
        if (cancelled) {
          return;
        }
        setDeckReady(false);
        setHasRendered(false);
        setFailureReason(null);
        viewer = new PPTXViewer({
          slideSizeMode: "fit",
          backgroundColor: "#ffffff",
          // The bundle defaults to exposing window.currentProcessor for chart
          // integration. This viewer stays self-contained instead.
          autoExposeGlobals: false,
        });
        viewerRef.current = viewer;
        await viewer.loadFile(data);
        if (cancelled || viewerRef.current !== viewer) {
          return;
        }
        const count = viewer.getSlideCount();
        if (count <= 0) {
          setFailureReason("");
          return;
        }
        setSlideCount(count);
        setSlideIndex(0);
        setDeckReady(true);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setFailureReason(errorReason(error));
      });

    return () => {
      cancelled = true;
      if (viewerRef.current === viewer) {
        viewerRef.current = null;
      }
      viewer?.destroy();
    };
  }, [data]);

  // Render the current slide, then re-render after a width change settles so
  // the canvas matches the container. A width of zero means the stage has not
  // been measured yet, so the effect waits for the next ResizeObserver report.
  const canvasWidth = containerWidth > 0 ? Math.floor(containerWidth) : 0;

  useEffect(() => {
    const viewer = viewerRef.current;
    const canvas = canvasRef.current;
    if (!deckReady || !viewer || !canvas || canvasWidth <= 0) {
      return;
    }
    let cancelled = false;
    const width = canvasWidth;
    const height = Math.round(width * slideAspect(viewer));
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    setRendering(true);

    void viewer
      .render(canvas, { slideIndex })
      .then(() => {
        if (cancelled) {
          return;
        }
        setHasRendered(true);
        setFailureReason(null);
        setRendering(false);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setRendering(false);
        setFailureReason(errorReason(error));
      });

    return () => {
      cancelled = true;
    };
  }, [canvasWidth, deckReady, slideIndex]);

  const showPrevious = useCallback(() => {
    setSlideIndex((current) => Math.max(0, current - 1));
  }, []);

  const showNext = useCallback(() => {
    setSlideIndex((current) => Math.min(Math.max(0, slideCount - 1), current + 1));
  }, [slideCount]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPrevious();
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      showNext();
    }
  };

  if (binaryQuery.isLoading) {
    return <ViewerLoading label={t("library.viewer.loading.pptxOriginal")} />;
  }

  if (binaryQuery.error) {
    return (
      <ViewerErrorState
        error={binaryQuery.error}
        title={t("library.viewer.pptx.errorOriginal")}
        onRetry={() => void binaryQuery.refetch()}
        downloadUrl={fileDownloadUrl(fileId)}
        downloadName={fileName}
      />
    );
  }

  if (failureReason !== null) {
    return (
      <ChunkFallback
        fileId={fileId}
        totalChunks={totalChunks}
        reason={t("library.viewer.pptx.renderFallback", {
          reason: failureReason || t("library.viewer.pptx.engineFallback"),
        })}
      />
    );
  }

  return (
    <div
      className="viewer-pptx"
      tabIndex={0}
      role="group"
      aria-label={t("library.viewer.pptx.frameTitle", { name: fileName })}
      onKeyDown={handleKeyDown}
    >
      <div className="viewer-notice" role="note">
        <span className="viewer-chip">{t("library.viewer.pptx.chip")}</span>
        <p>{t("library.viewer.pptx.notice")}</p>
      </div>
      <div className="viewer-pptx__bar">
        <div className="viewer-pptx__controls">
          <Button
            variant="ghost"
            size="sm"
            onClick={showPrevious}
            disabled={!deckReady || slideIndex <= 0}
            aria-label={t("library.viewer.pptx.previousSlide")}
            title={t("library.viewer.pptx.previousSlide")}
          >
            <span aria-hidden="true">←</span>
          </Button>
          <span className="viewer-pptx__counter" aria-hidden="true">
            {formatNumber(slideIndex + 1)} / {slideCount ? formatNumber(slideCount) : "—"}
          </span>
          <span className="visually-hidden" role="status" aria-live="polite">
            {deckReady
              ? t("library.viewer.pptx.slideOf", {
                  page: formatNumber(slideIndex + 1),
                  total: formatNumber(slideCount),
                })
              : ""}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={showNext}
            disabled={!deckReady || slideIndex >= slideCount - 1}
            aria-label={t("library.viewer.pptx.nextSlide")}
            title={t("library.viewer.pptx.nextSlide")}
          >
            <span aria-hidden="true">→</span>
          </Button>
        </div>
        <span className="viewer-pptx__hint">{t("library.viewer.pptx.keyboardHint")}</span>
      </div>
      <div className="viewer-pptx__stage" ref={setContainerElement}>
        {!deckReady || !hasRendered ? (
          <div className="viewer-pptx__overlay">
            <ViewerLoading label={t("library.viewer.loading.pptxLayout")} />
          </div>
        ) : null}
        <canvas
          ref={canvasRef}
          className="viewer-pptx__canvas"
          aria-label={t("library.viewer.pptx.canvasLabel", {
            page: formatNumber(slideIndex + 1),
            total: formatNumber(slideCount),
          })}
          role="img"
          aria-busy={rendering}
        />
      </div>
    </div>
  );
}
