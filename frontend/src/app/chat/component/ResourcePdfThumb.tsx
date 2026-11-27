import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Document, Page } from "react-pdf";

import { PDF_THUMB_OPTIONS } from "../../viewer/pdfjs-config";
import { useElementWidth } from "../../viewer/component/useElementWidth";
import { fileContentUrl } from "../../viewer/component/viewer-utils";
import { FileThumbnail } from "../../viewer/component/FileThumbnail";
import type { ThumbnailInfo } from "../../viewer/component/thumbnail";
import { PREVIEW_MAX_EDGE, framedThumbnailStyle } from "./resource-frame";

// Keep a portrait page readable without letting it dominate a wide transcript.
// The rendered width follows the card, so a phone gets a full-width page too.
const PREVIEW_MAX_WIDTH = PREVIEW_MAX_EDGE;

interface ResourcePdfThumbProps {
  readonly fileId: number;
  /** Server thumbnail of page 1: fixes the box size and paints first. */
  readonly thumbnail: ThumbnailInfo | null;
  readonly onError: () => void;
}

/**
 * The first page of a presented PDF, rendered inside the chat transcript.
 *
 * Loading waits until the card approaches the viewport, so a long transcript
 * does not fetch every PDF at once. A failed load reports to the parent, which
 * swaps in the server thumbnail or the ordinary file tile.
 *
 * With a server thumbnail the host box takes the thumbnail's aspect ratio and
 * paints it immediately; the sharper pdf.js canvas then draws over it at the
 * same size, so the card never changes height while loading.
 */
export const ResourcePdfThumb = memo(function ResourcePdfThumb({
  fileId,
  thumbnail,
  onError,
}: ResourcePdfThumbProps) {
  const [setMeasuredElement, measuredWidth] =
    useElementWidth<HTMLSpanElement>();
  const hostRef = useRef<HTMLSpanElement | null>(null);
  const setHost = useCallback(
    (element: HTMLSpanElement | null) => {
      hostRef.current = element;
      setMeasuredElement(element);
    },
    [setMeasuredElement],
  );
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

  const canMeasure = typeof ResizeObserver !== "undefined";
  const pageWidth =
    measuredWidth > 0
      ? Math.min(PREVIEW_MAX_WIDTH, Math.round(measuredWidth))
      : PREVIEW_MAX_WIDTH;
  const ready = visible && (measuredWidth > 0 || !canMeasure);
  // With a thumbnail underneath, pdf.js placeholders stay transparent so the
  // thumbnail remains visible until the canvas is drawn.
  const sheet =
    thumbnail === null ? <span className="chat-resource__pdf-sheet" /> : null;
  const pending =
    thumbnail === null ? <span className="chat-resource__pdf-pending" /> : null;

  return (
    <span
      ref={setHost}
      className={
        thumbnail === null
          ? "chat-resource__thumb chat-resource__thumb--pdf"
          : "chat-resource__thumb chat-resource__thumb--pdf chat-resource__thumb--framed"
      }
      style={thumbnail === null ? undefined : framedThumbnailStyle(thumbnail)}
      aria-hidden="true"
    >
      {thumbnail === null ? null : (
        <FileThumbnail
          fileId={fileId}
          thumbnail={thumbnail}
          sizing="fill"
          className="chat-resource__pdf-base"
        />
      )}
      {ready ? (
        <Document
          file={fileContentUrl(fileId)}
          options={PDF_THUMB_OPTIONS}
          loading={sheet}
          error={sheet}
          onLoadError={() => onErrorRef.current()}
        >
          <Page
            pageNumber={1}
            width={pageWidth}
            devicePixelRatio={Math.min(window.devicePixelRatio || 1, 2)}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            loading={sheet}
            error={sheet}
            onLoadError={() => onErrorRef.current()}
            onRenderError={() => onErrorRef.current()}
          />
        </Document>
      ) : (
        pending
      )}
    </span>
  );
});
