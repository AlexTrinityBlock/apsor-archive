import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
} from "react";
import { Document, Page, pdfjs } from "react-pdf";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?worker&url";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import "react-pdf/dist/Page/TextLayer.css";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";
import { ViewerErrorState } from "./ViewerStates";
import { useElementWidth } from "./useElementWidth";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface PdfViewProps {
  readonly fileUrl: string;
  readonly fileName: string;
  readonly downloadUrl: string;
}

// PDF.js 6 no longer exposes the eval flag in its public type and has dropped
// runtime eval. Keep the flag pinned defensively if an engine still reads it,
// without weakening the type boundary for every other option.
//
// The document is loaded from its URL, not as an ArrayBuffer, so PDF.js can use
// the API's byte-range support. Its first request is a header probe;
// `disableStream` cancels that full response, and `disableAutoFetch` stops the
// worker from prefetching chunks for pages that are not being rendered. Both
// flags are required for true range loading. `rangeChunkSize` trades request
// count against the size of each lazy fetch.
const PDF_OPTIONS = {
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
  isEvalSupported: false,
  withCredentials: true,
  rangeChunkSize: 256 * 1024,
  disableStream: true,
  disableAutoFetch: true,
} as unknown as NonNullable<ComponentProps<typeof Document>["options"]>;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const DEFAULT_PAGE_ASPECT = 1.414;
const FALLBACK_PAGE_WIDTH = 612;
// The mount window is measured in page heights rather than screen heights, so
// tall desktop pages and short phone pages both keep only a few canvases alive.
const PAGE_MOUNT_HEIGHT_RATIO = 0.6;
const PAGE_MOUNT_MIN = 220;
const PAGE_MOUNT_MAX = 720;
// A narrow band near the top of the scroll owner decides which page is
// "current". The band sits below the sticky toolbar and above the bulk of the
// page, so the counter follows the page being read rather than the page edge
// that happens to touch the bottom of the viewport.
const PAGE_READING_BAND = "-10% 0px -80% 0px";
const PAGE_READING_THRESHOLDS = [0, 0.01, 0.05, 0.1, 0.25, 0.5, 1];

interface PdfPageShellProps {
  readonly pageNumber: number;
  readonly width: number;
  readonly aspectRatio: number;
  readonly mounted: boolean;
  readonly onPageLoad: (pageNumber: number, page: PDFPageProxy) => void;
}

/**
 * One page slot in the continuous scroll surface.
 *
 * The slot is rendered for every page as soon as the document reports its page
 * count. Only slots near the viewport mount a PDF.js `<Page>`; the rest keep a
 * correctly sized placeholder, so the scrollbar and reading position are stable
 * without paying for hundreds of canvases. Memoizing the slot means scrolling
 * only re-renders the pages that enter or leave the mounted window.
 */
const PdfPageShell = memo(function PdfPageShell({
  pageNumber,
  width,
  aspectRatio,
  mounted,
  onPageLoad,
}: PdfPageShellProps) {
  return (
    <div
      className="viewer-pdf__page-shell"
      data-pdf-page={pageNumber}
      style={{
        width: `${width}px`,
        minHeight: `${Math.round(width * aspectRatio)}px`,
      }}
    >
      {mounted ? (
        <Page
          pageNumber={pageNumber}
          width={width}
          renderTextLayer
          renderAnnotationLayer={false}
          canvasBackground="#fdfaf3"
          loading={
            <span className="viewer-pdf__page-note" aria-hidden="true">
              {pageNumber}
            </span>
          }
          onLoadSuccess={(page) => onPageLoad(pageNumber, page)}
        />
      ) : (
        <div
          className="viewer-pdf__page-placeholder"
          style={{ aspectRatio: `1 / ${aspectRatio}` }}
          aria-hidden="true"
        >
          <span className="viewer-pdf__page-note">{pageNumber}</span>
        </div>
      )}
    </div>
  );
});

/** Read the page number from a rendered shell. */
function pageNumberFrom(target: Element): number | null {
  if (!(target instanceof HTMLElement)) {
    return null;
  }
  const page = Number(target.dataset.pdfPage);
  return Number.isInteger(page) && page > 0 ? page : null;
}

/** Find the element that actually owns vertical scrolling for a surface. */
function findScrollOwner(element: HTMLElement | null): HTMLElement | null {
  let node = element;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    if (overflowY === "auto" || overflowY === "scroll") {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

/**
 * PDF.js viewer with continuous, lazy page rendering, zoom, fit width, and a
 * selectable text layer. The original is fetched through PDF.js range requests,
 * so opening a large document does not download all of it. Evaluation is
 * disabled; the worker is bundled through Vite's URL import so the viewer never
 * fetches a remote script.
 */
export function PdfView({ fileUrl, fileName, downloadUrl }: PdfViewProps) {
  const { t, formatNumber } = useI18n();
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageWidth, setPageWidth] = useState<number | null>(null);
  const [pageAspect, setPageAspect] = useState(DEFAULT_PAGE_ASPECT);
  const [pageAspects, setPageAspects] = useState<ReadonlyMap<number, number>>(
    () => new Map<number, number>(),
  );
  const [mountedPages, setMountedPages] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const [scale, setScale] = useState(1);
  const [fitWidth, setFitWidth] = useState(true);
  const [documentError, setDocumentError] = useState<Error | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const currentPageRef = useRef(1);
  // Fullscreen changes the scroll owner and the fitted page width, so the
  // reading position is re-anchored until the user touches the document.
  const anchorPageRef = useRef<number | null>(null);
  const [setMeasuredElement, containerWidth] = useElementWidth<HTMLDivElement>();

  const setScrollElement = useCallback(
    (element: HTMLDivElement | null) => {
      scrollRef.current = element;
      setMeasuredElement(element);
    },
    [setMeasuredElement],
  );

  const updateCurrentPage = useCallback((page: number) => {
    currentPageRef.current = page;
    // While a fullscreen/zoom re-anchor is armed, follow the reading position
    // so a later width change lands on the page the user actually reached.
    if (anchorPageRef.current !== null) {
      anchorPageRef.current = page;
    }
    setCurrentPage(page);
  }, []);

  const fullscreenActive = fullscreen && numPages > 0 && !documentError;

  useScrollLock(fullscreenActive);

  // Native fullscreen is an enhancement: desktop and Android can hide the
  // browser chrome, while iOS Safari falls back to the in-app overlay.
  useEffect(() => {
    const handleFullscreenChange = () => {
      if (document.fullscreenElement !== viewerRef.current) {
        anchorPageRef.current = currentPageRef.current;
        setFullscreen(false);
      }
    };
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () =>
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const leaveFullscreen = useCallback(() => {
    anchorPageRef.current = currentPageRef.current;
    if (document.fullscreenElement === viewerRef.current) {
      void document.exitFullscreen().catch(() => undefined);
    }
    setFullscreen(false);
  }, []);

  const toggleFullscreen = () => {
    if (fullscreenActive) {
      leaveFullscreen();
      return;
    }
    anchorPageRef.current = currentPageRef.current;
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
        leaveFullscreen();
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
  }, [fullscreenActive, leaveFullscreen]);

  const fitPageWidth = Math.max(
    280,
    containerWidth > 0 ? containerWidth - 48 : 280,
  );
  const fitScale =
    pageWidth !== null && pageWidth > 0 ? fitPageWidth / pageWidth : 1;
  const activeScale = fitWidth ? fitScale : scale;
  const renderedWidth = fitWidth
    ? fitPageWidth
    : Math.max(120, (pageWidth ?? FALLBACK_PAGE_WIDTH) * scale);
  const mountMargin = `${Math.round(
    Math.min(
      PAGE_MOUNT_MAX,
      Math.max(
        PAGE_MOUNT_MIN,
        renderedWidth * pageAspect * PAGE_MOUNT_HEIGHT_RATIO,
      ),
    ),
  )}px 0px`;

  // Mount pages near the scroll owner's viewport. Normal mode scrolls the
  // modal body while fullscreen makes the PDF surface its own scroll owner, so
  // the observer follows whichever element actually scrolls.
  useEffect(() => {
    const surface = scrollRef.current;
    if (!surface || numPages === 0) {
      return;
    }
    const shells = surface.querySelectorAll<HTMLElement>("[data-pdf-page]");
    if (shells.length === 0) {
      return;
    }
    const mounted = new Set<number>();
    const observer = new IntersectionObserver(
      (entries) => {
        let changed = false;
        for (const entry of entries) {
          const page = pageNumberFrom(entry.target);
          if (page === null) {
            continue;
          }
          if (entry.isIntersecting) {
            if (!mounted.has(page)) {
              mounted.add(page);
              changed = true;
            }
          } else if (mounted.delete(page)) {
            changed = true;
          }
        }
        if (changed) {
          setMountedPages(new Set(mounted));
        }
      },
      {
        root: findScrollOwner(surface),
        rootMargin: mountMargin,
        threshold: 0,
      },
    );
    shells.forEach((shell) => observer.observe(shell));
    return () => observer.disconnect();
  }, [numPages, fullscreenActive, mountMargin]);

  // Track the page that owns the reading band. This is what drives the page
  // counter; scrolling is the only page navigation control. The intersection
  // height is tracked per page so scrolling back up flips the counter at the
  // page boundary instead of leaving it on the page that just left.
  useEffect(() => {
    const surface = scrollRef.current;
    if (!surface || numPages === 0) {
      return;
    }
    const shells = surface.querySelectorAll<HTMLElement>("[data-pdf-page]");
    if (shells.length === 0) {
      return;
    }
    const overlaps = new Map<number, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const page = pageNumberFrom(entry.target);
          if (page === null) {
            continue;
          }
          overlaps.set(
            page,
            entry.isIntersecting ? entry.intersectionRect.height : 0,
          );
        }
        let nextPage = 0;
        let nextOverlap = 0;
        for (const [page, overlap] of overlaps) {
          if (overlap > nextOverlap) {
            nextOverlap = overlap;
            nextPage = page;
          }
        }
        if (nextPage > 0) {
          updateCurrentPage(nextPage);
        }
      },
      {
        root: findScrollOwner(surface),
        rootMargin: PAGE_READING_BAND,
        threshold: PAGE_READING_THRESHOLDS,
      },
    );
    shells.forEach((shell) => observer.observe(shell));
    return () => observer.disconnect();
  }, [numPages, fullscreenActive, updateCurrentPage]);

  const handleDocumentLoad = useCallback(
    (document: PDFDocumentProxy) => {
      setNumPages(document.numPages);
      updateCurrentPage(1);
      setMountedPages(new Set<number>());
      setPageWidth(null);
      setPageAspect(DEFAULT_PAGE_ASPECT);
      setPageAspects(new Map<number, number>());
      setDocumentError(null);
      anchorPageRef.current = null;
      const owner = findScrollOwner(scrollRef.current);
      if (owner) {
        owner.scrollTop = 0;
      }
    },
    [updateCurrentPage],
  );

  const handleDocumentError = useCallback((error: Error) => {
    // PDF.js reports HTTP failures as an Error, not a Response. Preserve the
    // archive's session-expiry path instead of leaving the modal on a dead view.
    if (/\b401\b/.test(error.message)) {
      window.dispatchEvent(new Event("apsor-archive:unauthorized"));
    }
    anchorPageRef.current = null;
    const owner = findScrollOwner(scrollRef.current);
    if (owner) {
      owner.scrollTop = 0;
    }
    setFullscreen(false);
    setDocumentError(error);
    if (document.fullscreenElement === viewerRef.current) {
      void document.exitFullscreen().catch(() => undefined);
    }
  }, []);

  const handlePageLoad = useCallback(
    (pageNumber: number, page: PDFPageProxy) => {
      const viewport = page.getViewport({ scale: 1 });
      if (viewport.width <= 0 || viewport.height <= 0) {
        return;
      }
      const aspect = viewport.height / viewport.width;
      setPageAspects((previous) => {
        const measured = previous.get(pageNumber);
        if (measured !== undefined && Math.abs(measured - aspect) < 0.0001) {
          return previous;
        }
        const next = new Map(previous);
        next.set(pageNumber, aspect);
        return next;
      });
      // Page one supplies the document's reference width and the fallback
      // shape for pages that have not been measured yet. Recording it only once
      // keeps later page loads from re-laying out the whole stream.
      if (pageNumber === 1) {
        setPageAspect((previous) =>
          Math.abs(previous - aspect) < 0.0001 ? previous : aspect,
        );
        setPageWidth((previous) => previous ?? viewport.width);
      }
    },
    [],
  );

  const pageNumbers = useMemo(
    () => Array.from({ length: numPages }, (_, index) => index + 1),
    [numPages],
  );

  /**
   * Put a page at the top of the active scroll owner. Used when fullscreen
   * changes the owner and the fitted page width, so the reading position does
   * not jump back to page one.
   */
  const scrollPageToReadingOffset = useCallback((pageNumber: number) => {
    const surface = scrollRef.current;
    if (!surface) {
      return;
    }
    const shell = surface.querySelector<HTMLElement>(
      `[data-pdf-page="${pageNumber}"]`,
    );
    if (!shell) {
      return;
    }
    const owner = findScrollOwner(surface);
    if (!owner) {
      return;
    }
    // The toolbar is a sibling of the scroll surface, not a descendant, so
    // look it up from the viewer when the modal body is the scroll owner.
    const toolbarHeight =
      owner === surface
        ? 0
        : (surface
            .closest(".viewer-pdf")
            ?.querySelector<HTMLElement>(".viewer-pdf__bar")?.offsetHeight ?? 0);
    const ownerTop = owner.getBoundingClientRect().top;
    const shellTop = shell.getBoundingClientRect().top;
    owner.scrollTop += shellTop - ownerTop - toolbarHeight;
  }, []);

  // Re-anchor after fullscreen's first paint and again when the fitted width
  // has settled. The anchor follows the reading position for later width
  // changes; any direct interaction with the document clears it below.
  useLayoutEffect(() => {
    const page = anchorPageRef.current;
    if (page === null || numPages === 0) {
      return;
    }
    scrollPageToReadingOffset(page);
  }, [fullscreenActive, numPages, renderedWidth, scrollPageToReadingOffset]);

  useEffect(() => {
    const surface = scrollRef.current;
    if (!surface) {
      return;
    }
    const owner = findScrollOwner(surface) ?? surface;
    const clearAnchor = () => {
      anchorPageRef.current = null;
    };
    owner.addEventListener("wheel", clearAnchor, { passive: true });
    owner.addEventListener("touchstart", clearAnchor, { passive: true });
    owner.addEventListener("pointerdown", clearAnchor);
    owner.addEventListener("keydown", clearAnchor);
    return () => {
      owner.removeEventListener("wheel", clearAnchor);
      owner.removeEventListener("touchstart", clearAnchor);
      owner.removeEventListener("pointerdown", clearAnchor);
      owner.removeEventListener("keydown", clearAnchor);
    };
  }, [fullscreenActive, documentError]);

  const zoomBy = (delta: number) => {
    const current = fitWidth ? fitScale : scale;
    anchorPageRef.current = currentPageRef.current;
    setFitWidth(false);
    setScale(Math.min(4, Math.max(0.2, current + delta)));
  };

  const retryDocument = () => {
    setDocumentError(null);
    setNumPages(0);
    updateCurrentPage(1);
    setMountedPages(new Set<number>());
    setPageWidth(null);
    setPageAspect(DEFAULT_PAGE_ASPECT);
    setPageAspects(new Map<number, number>());
    anchorPageRef.current = null;
    setReloadKey((current) => current + 1);
  };

  if (documentError) {
    return (
      <ViewerErrorState
        error={documentError}
        title={t("library.viewer.pdf.errorOriginal")}
        onRetry={retryDocument}
        downloadUrl={downloadUrl}
        downloadName={fileName}
      />
    );
  }

  return (
    <div
      ref={viewerRef}
      className={`viewer-pdf${fullscreenActive ? " viewer-pdf--fullscreen" : ""}${
        numPages === 0 ? " viewer-pdf--loading" : ""
      }`}
      role={fullscreenActive ? "dialog" : undefined}
      aria-modal={fullscreenActive ? true : undefined}
      aria-label={fullscreenActive ? fileName : undefined}
      tabIndex={fullscreenActive ? -1 : undefined}
    >
      <div className="viewer-pdf__bar">
        <div className="viewer-pdf__group viewer-pdf__page-status">
          <Icon
            name="chevron-down"
            size={14}
            className="viewer-pdf__scroll-icon"
          />
          <span className="viewer-pdf__scroll-hint">
            {t("library.viewer.pdf.scrollHint")}
          </span>
          <span className="viewer-pdf__page-count" aria-hidden="true">
            {formatNumber(currentPage)} /{" "}
            {numPages ? formatNumber(numPages) : "—"}
          </span>
          <span className="visually-hidden" role="status" aria-live="polite">
            {numPages
              ? t("library.viewer.pdf.pageOf", {
                  page: formatNumber(currentPage),
                  total: formatNumber(numPages),
                })
              : ""}
          </span>
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
              anchorPageRef.current = currentPageRef.current;
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
            onClick={() => {
              anchorPageRef.current = currentPageRef.current;
              setFitWidth(true);
            }}
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

      <div
        className="viewer-pdf__scroll"
        ref={setScrollElement}
        tabIndex={0}
        role="region"
        aria-label={fileName}
      >
        <Document
          key={reloadKey}
          file={fileUrl}
          options={PDF_OPTIONS}
          loading={
            <p className="viewer-pdf__message">
              {t("library.viewer.loading.pdfPages")}
            </p>
          }
          onLoadSuccess={handleDocumentLoad}
          onLoadError={handleDocumentError}
          onSourceError={handleDocumentError}
          error={null}
          noData={null}
          suspense={false}
        >
          <div className="viewer-pdf__pages">
            {pageNumbers.map((pageNumber) => (
              <PdfPageShell
                key={pageNumber}
                pageNumber={pageNumber}
                width={renderedWidth}
                aspectRatio={pageAspects.get(pageNumber) ?? pageAspect}
                mounted={mountedPages.has(pageNumber)}
                onPageLoad={handlePageLoad}
              />
            ))}
          </div>
        </Document>
      </div>

      <p className="viewer-pdf__foot">
        {t("library.viewer.pdf.foot", { version: pdfjs.version })}
      </p>
    </div>
  );
}
