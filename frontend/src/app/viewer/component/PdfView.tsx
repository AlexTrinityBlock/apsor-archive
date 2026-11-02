import { useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import { useQuery } from "@tanstack/react-query";
import { Document, Page, pdfjs } from "react-pdf";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?worker&url";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";
import { ViewerErrorState, ViewerLoading } from "./ViewerStates";
import { useElementWidth } from "./useElementWidth";
import { fetchViewerBinary } from "./viewer-utils";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface PdfViewProps {
  readonly fileId: number;
  readonly fileUrl: string;
  readonly fileName: string;
  readonly downloadUrl: string;
}

// pdfjs-dist 6 no longer exposes the eval flag in its public type and has
// dropped runtime eval. Keep the flag pinned defensively if an engine still
// reads it, without weakening the type boundary for every other option.
const PDF_OPTIONS = {
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
  isEvalSupported: false,
} as unknown as NonNullable<ComponentProps<typeof Document>["options"]>;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * PDF.js viewer with page navigation, zoom, fit width, and a selectable text
 * layer. PDF evaluation is disabled; the worker is bundled through Vite's URL
 * import so the viewer never fetches a remote script.
 */
export function PdfView({ fileId, fileUrl, fileName, downloadUrl }: PdfViewProps) {
  const { t, formatNumber } = useI18n();
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1);
  const [fitWidth, setFitWidth] = useState(true);
  const [pageWidth, setPageWidth] = useState<number | null>(null);
  const [documentError, setDocumentError] = useState<Error | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const [setScrollElement, containerWidth] = useElementWidth<HTMLDivElement>();

  const binaryQuery = useQuery({
    queryKey: ["viewer", "file-binary", fileId],
    queryFn: ({ signal }) => fetchViewerBinary(fileUrl, signal),
    retry: false,
    staleTime: 5 * 60_000,
  });

  // Copy the buffer because PDF.js may transfer its backing store to the worker.
  const documentSource = useMemo(() => {
    if (!binaryQuery.data) {
      return null;
    }
    return { data: new Uint8Array(binaryQuery.data.slice(0)) };
  }, [binaryQuery.data]);

  const fullscreenActive =
    fullscreen &&
    documentSource !== null &&
    !binaryQuery.isLoading &&
    !binaryQuery.error &&
    !documentError;

  useScrollLock(fullscreenActive);

  // Native fullscreen is an enhancement: desktop and Android can hide the
  // browser chrome, while iOS Safari falls back to the in-app overlay.
  useEffect(() => {
    const handleFullscreenChange = () => {
      if (document.fullscreenElement !== viewerRef.current) {
        setFullscreen(false);
      }
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () =>
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const toggleFullscreen = () => {
    if (fullscreenActive) {
      if (document.fullscreenElement) {
        void document.exitFullscreen().catch(() => undefined);
      }
      setFullscreen(false);
      return;
    }
    setFullscreen(true);
    const viewer = viewerRef.current;
    if (!viewer || typeof viewer.requestFullscreen !== "function") {
      return;
    }
    void viewer.requestFullscreen().catch(() => undefined);
  };

  // Fullscreen is a viewing mode, not a second dialog: Escape leaves it
  // without closing the preview underneath, and Tab stays inside the viewer so
  // the modal's own focus trap cannot jump to controls hidden behind it.
  useEffect(() => {
    if (!fullscreenActive) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (document.fullscreenElement) {
          void document.exitFullscreen().catch(() => undefined);
        }
        setFullscreen(false);
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      event.stopPropagation();
      const viewer = viewerRef.current;
      if (!viewer) {
        return;
      }
      const focusable = Array.from(
        viewer.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        viewer.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (!viewer.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [fullscreenActive]);

  const fitScale =
    pageWidth !== null && containerWidth > 0
      ? Math.max(0.2, (containerWidth - 48) / pageWidth)
      : 1;
  const activeScale = fitWidth ? fitScale : scale;

  const setPage = (next: number) => {
    if (numPages === 0) {
      return;
    }
    setPageNumber(Math.min(numPages, Math.max(1, next)));
  };

  const zoomBy = (delta: number) => {
    const current = fitWidth ? fitScale : scale;
    setFitWidth(false);
    setScale(Math.min(4, Math.max(0.2, current + delta)));
  };

  if (binaryQuery.isLoading) {
    return <ViewerLoading label={t("library.viewer.loading.pdfOriginal")} />;
  }

  if (binaryQuery.error) {
    return (
      <ViewerErrorState
        error={binaryQuery.error}
        title={t("library.viewer.pdf.errorOriginal")}
        onRetry={() => void binaryQuery.refetch()}
        downloadUrl={downloadUrl}
        downloadName={fileName}
      />
    );
  }

  if (!documentSource) {
    return null;
  }

  if (documentError) {
    return (
      <ViewerErrorState
        error={documentError}
        title={t("library.viewer.pdf.errorLayout")}
        onRetry={() => setDocumentError(null)}
        downloadUrl={downloadUrl}
        downloadName={fileName}
      />
    );
  }

  return (
    <div
      ref={viewerRef}
      className={
        fullscreenActive ? "viewer-pdf viewer-pdf--fullscreen" : "viewer-pdf"
      }
      role={fullscreenActive ? "dialog" : undefined}
      aria-modal={fullscreenActive ? true : undefined}
      aria-label={fullscreenActive ? fileName : undefined}
      tabIndex={fullscreenActive ? -1 : undefined}
    >
      <div className="viewer-pdf__bar">
        <div className="viewer-pdf__group">
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            onClick={() => setPage(pageNumber - 1)}
            disabled={pageNumber <= 1}
            aria-label={t("library.viewer.pdf.previousPage")}
            title={t("library.viewer.pdf.previousPage")}
          >
            <Icon name="chevron-right" size={16} className="viewer-back-icon" />
          </Button>
          <label className="viewer-pdf__page-field">
            <span className="visually-hidden">{t("library.viewer.pdf.pageNumber")}</span>
            <input
              type="number"
              min={1}
              max={Math.max(1, numPages)}
              value={pageNumber}
              onChange={(event) => setPage(Number(event.target.value))}
              aria-label={t("library.viewer.pdf.pageNumber")}
            />
            <span aria-hidden="true">/ {numPages ? formatNumber(numPages) : "—"}</span>
          </label>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            onClick={() => setPage(pageNumber + 1)}
            disabled={numPages === 0 || pageNumber >= numPages}
            aria-label={t("library.viewer.pdf.nextPage")}
            title={t("library.viewer.pdf.nextPage")}
          >
            <Icon name="chevron-right" size={16} />
          </Button>
        </div>

        <div className="viewer-pdf__group">
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            onClick={() => zoomBy(-0.15)}
            aria-label={t("library.viewer.zoomOut")}
            title={t("library.viewer.zoomOut")}
          >
            <span aria-hidden="true">−</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="viewer-pdf__zoom"
            onClick={() => {
              setFitWidth(false);
              setScale(1);
            }}
            aria-label={t("library.viewer.pdf.resetZoomLabel", {
              value: formatNumber(Math.round(activeScale * 100)),
            })}
            title={t("library.viewer.pdf.resetZoom")}
          >
            {formatNumber(Math.round(activeScale * 100))}%
          </Button>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            onClick={() => zoomBy(0.15)}
            aria-label={t("library.viewer.zoomIn")}
            title={t("library.viewer.zoomIn")}
          >
            <span aria-hidden="true">+</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFitWidth(true)}
            aria-pressed={fitWidth}
          >
            {t("library.viewer.pdf.fitWidth")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            iconOnly
            className="viewer-pdf__fullscreen"
            onClick={toggleFullscreen}
            aria-label={t(
              fullscreenActive
                ? "library.viewer.pdf.exitFullscreen"
                : "library.viewer.pdf.enterFullscreen",
            )}
            title={t(
              fullscreenActive
                ? "library.viewer.pdf.exitFullscreen"
                : "library.viewer.pdf.enterFullscreen",
            )}
            aria-pressed={fullscreenActive}
          >
            <Icon
              name={fullscreenActive ? "minimize" : "maximize"}
              size={16}
            />
          </Button>
        </div>
      </div>

      <div className="viewer-pdf__scroll" ref={setScrollElement}>
        <Document
          file={documentSource}
          options={PDF_OPTIONS}
          loading={<ViewerLoading label={t("library.viewer.loading.pdfPages")} />}
          onLoadSuccess={(document) => {
            setNumPages(document.numPages);
            setPageNumber(1);
            setDocumentError(null);
          }}
          onLoadError={(error) => setDocumentError(error)}
          onSourceError={(error) => setDocumentError(error)}
          error={null}
          noData={null}
          suspense={false}
        >
          <Page
            key={`${pageNumber}-${fitWidth ? "fit" : "zoom"}`}
            pageNumber={pageNumber}
            width={
              fitWidth && containerWidth > 0
                ? Math.max(280, containerWidth - 48)
                : undefined
            }
            scale={fitWidth ? undefined : scale}
            renderTextLayer
            renderAnnotationLayer={false}
            canvasBackground="#fdfaf3"
            loading={
              <ViewerLoading
                label={t("library.viewer.loading.pdfPage", { page: pageNumber })}
              />
            }
            onLoadSuccess={(page) => {
              const width = page.getViewport({ scale: 1 }).width;
              if (width > 0) {
                setPageWidth(width);
              }
            }}
          />
        </Document>
      </div>

      <p className="viewer-pdf__foot">
        {t("library.viewer.pdf.foot", { version: pdfjs.version })}
      </p>
    </div>
  );
}
