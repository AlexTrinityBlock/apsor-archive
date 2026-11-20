import {
  useEffect,
  useRef,
  useState,
  type ComponentProps,
} from "react";
import { Document, Page, pdfjs } from "react-pdf";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?worker&url";

import { fileContentUrl } from "../../viewer/component/viewer-utils";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

// The bubble only needs the first page as a still image. Range loading keeps
// the request small for large PDFs, and both layers are disabled because the
// thumbnail is not interactive.
const PDF_THUMB_OPTIONS = {
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
  isEvalSupported: false,
  withCredentials: true,
  rangeChunkSize: 256 * 1024,
  disableStream: true,
  disableAutoFetch: true,
} as unknown as NonNullable<ComponentProps<typeof Document>["options"]>;

// Render at 2x the visible width and scale down in CSS so the page stays sharp
// on high-density screens without changing the 58 × 78 bubble slot.
const THUMB_RENDER_WIDTH = 116;

interface ResourcePdfThumbProps {
  readonly fileId: number;
  readonly onError: () => void;
}

/**
 * The first page of a presented PDF, rendered inside the chat bubble.
 *
 * Loading waits until the bubble approaches the viewport, so a long transcript
 * does not fetch every PDF at once. A failed load reports to the parent, which
 * swaps in the ordinary file tile.
 */
export function ResourcePdfThumb({
  fileId,
  onError,
}: ResourcePdfThumbProps) {
  const hostRef = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    if (visible) {
      return;
    }
    const host = hostRef.current;
    if (host === null) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "240px 0px" },
    );
    observer.observe(host);
    return () => observer.disconnect();
  }, [visible]);

  return (
    <span
      ref={hostRef}
      className="chat-resource__thumb chat-resource__thumb--pdf"
      aria-hidden="true"
    >
      {visible ? (
        <Document
          file={fileContentUrl(fileId)}
          options={PDF_THUMB_OPTIONS}
          loading={<span className="chat-resource__pdf-sheet" />}
          error={<span className="chat-resource__pdf-sheet" />}
          onLoadError={() => onErrorRef.current()}
        >
          <Page
            pageNumber={1}
            width={THUMB_RENDER_WIDTH}
            devicePixelRatio={Math.min(window.devicePixelRatio || 1, 2)}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            loading={<span className="chat-resource__pdf-sheet" />}
            error={<span className="chat-resource__pdf-sheet" />}
            onLoadError={() => onErrorRef.current()}
            onRenderError={() => onErrorRef.current()}
          />
        </Document>
      ) : (
        <span className="chat-resource__pdf-pending" />
      )}
    </span>
  );
}
