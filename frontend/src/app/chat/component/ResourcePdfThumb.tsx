import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Document, Page } from "react-pdf";

import { PDF_THUMB_OPTIONS } from "../../viewer/pdfjs-config";
import { useElementWidth } from "../../viewer/component/useElementWidth";
import { fileContentUrl } from "../../viewer/component/viewer-utils";

// Keep a portrait page readable without letting it dominate a wide transcript.
// The rendered width follows the card, so a phone gets a full-width page too.
const PREVIEW_MAX_WIDTH = 420;

interface ResourcePdfThumbProps {
  readonly fileId: number;
  readonly onError: () => void;
}

/**
 * The first page of a presented PDF, rendered inside the chat transcript.
 *
 * Loading waits until the card approaches the viewport, so a long transcript
 * does not fetch every PDF at once. A failed load reports to the parent, which
 * swaps in the ordinary file tile.
 */
export const ResourcePdfThumb = memo(function ResourcePdfThumb({
  fileId,
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

  return (
    <span
      ref={setHost}
      className="chat-resource__thumb chat-resource__thumb--pdf"
      aria-hidden="true"
    >
      {ready ? (
        <Document
          file={fileContentUrl(fileId)}
          options={PDF_THUMB_OPTIONS}
          loading={<span className="chat-resource__pdf-sheet" />}
          error={<span className="chat-resource__pdf-sheet" />}
          onLoadError={() => onErrorRef.current()}
        >
          <Page
            pageNumber={1}
            width={pageWidth}
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
});
