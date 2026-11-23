import { useEffect, useRef, useState } from "react";
import { Document, Page } from "react-pdf";

import { PDF_THUMB_OPTIONS } from "../../viewer/pdfjs-config";
import { fileContentUrl } from "../../viewer/component/viewer-utils";

// The page is rendered at the bubble's visible width. PDF.js backs the canvas
// with devicePixelRatio pixels, so the thumbnail stays sharp on high-density
// screens without a CSS transform.
const THUMB_RENDER_WIDTH = 58;

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
