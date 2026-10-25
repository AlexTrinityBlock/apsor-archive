import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { renderAsync } from "docx-preview";

import { ChunkFallback } from "./ChunkFallback";
import { ViewerErrorState, ViewerLoading } from "./ViewerStates";
import { fetchViewerBinary, fileDownloadUrl } from "./viewer-utils";
import { useI18n } from "../../i18n";

interface DocxViewProps {
  readonly fileId: number;
  readonly fileUrl: string;
  readonly fileName: string;
  readonly totalChunks: number;
}

const DOCX_FRAME = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none';">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      html, body { margin: 0; padding: 0; background: #f3edde; }
      body { min-height: 100vh; }
    </style>
  </head>
  <body></body>
</html>`;

const DOCX_OPTIONS = {
  inWrapper: true,
  breakPages: true,
  ignoreWidth: false,
  ignoreHeight: true,
  ignoreFonts: false,
  renderHeaders: true,
  renderFooters: true,
  renderFootnotes: true,
  renderEndnotes: true,
  useBase64URL: true,
  renderChanges: false,
  renderComments: false,
  renderAltChunks: false,
  hideWrapperOnPrint: true,
} as const;

function hardenFrame(document: Document) {
  document.querySelectorAll("script, iframe, object, embed, link, base").forEach((node) => {
    node.remove();
  });
  document.querySelectorAll("meta[http-equiv='refresh' i]").forEach((node) => node.remove());
  document.querySelectorAll<HTMLAnchorElement>("a[href]").forEach((link) => {
    if (link.protocol !== "http:" && link.protocol !== "https:") {
      link.removeAttribute("href");
      return;
    }
    link.target = "_blank";
    link.rel = "noopener noreferrer nofollow";
  });
  document.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      if (attribute.name.toLowerCase().startsWith("on")) {
        element.removeAttribute(attribute.name);
      }
    }
  });
}

/**
 * DOCX preview is rendered inside a sandboxed iframe with scripts disabled.
 * The parent only touches the frame document to run `docx-preview`, strip
 * active elements, and fit the frame height; no innerHTML is written by this
 * component. If layout fails, the indexed chunks remain readable.
 */
export function DocxView({ fileId, fileUrl, fileName, totalChunks }: DocxViewProps) {
  const { t } = useI18n();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [frameReady, setFrameReady] = useState(false);
  const [rendering, setRendering] = useState(true);
  const [renderError, setRenderError] = useState<string | null>(null);

  const binaryQuery = useQuery({
    queryKey: ["viewer", "file-binary", fileId],
    queryFn: ({ signal }) => fetchViewerBinary(fileUrl, signal),
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !frameReady || !binaryQuery.data) {
      return;
    }
    const frameDocument = iframe.contentDocument;
    if (!frameDocument) {
      setRenderError(t("library.viewer.docx.frameUnavailable"));
      setRendering(false);
      return;
    }

    const body = frameDocument.body;
    const head = frameDocument.head;
    let cancelled = false;
    setRendering(true);
    setRenderError(null);
    body.replaceChildren();
    head.querySelectorAll("style").forEach((style) => style.remove());

    const resize = () => {
      if (!cancelled) {
        iframe.style.height = `${Math.min(20_000, Math.max(480, body.scrollHeight + 24))}px`;
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(body);

    const source = binaryQuery.data.slice(0);
    void renderAsync(source, body, head, { ...DOCX_OPTIONS })
      .then(() => {
        if (cancelled) {
          return;
        }
        hardenFrame(frameDocument);
        setRendering(false);
        window.requestAnimationFrame(resize);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setRendering(false);
        setRenderError(
          error instanceof Error && error.message.length > 0
            ? error.message
            : t("library.viewer.docx.engineFallback"),
        );
      });

    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, [binaryQuery.data, frameReady, t]);

  if (binaryQuery.isLoading) {
    return <ViewerLoading label={t("library.viewer.loading.docxOriginal")} />;
  }

  if (binaryQuery.error) {
    return (
      <ViewerErrorState
        error={binaryQuery.error}
        title={t("library.viewer.docx.errorOriginal")}
        onRetry={() => void binaryQuery.refetch()}
        downloadUrl={fileDownloadUrl(fileId)}
        downloadName={fileName}
      />
    );
  }

  if (renderError) {
    return (
      <ChunkFallback
        fileId={fileId}
        totalChunks={totalChunks}
        reason={t("library.viewer.docx.renderFallback", { reason: renderError })}
      />
    );
  }

  return (
    <div className="viewer-docx">
      <div className="viewer-notice" role="note">
        <span className="viewer-chip">{t("library.viewer.docx.chip")}</span>
        <p>{t("library.viewer.docx.notice")}</p>
      </div>
      <div className="viewer-docx__frame-wrap">
        {rendering ? (
          <div className="viewer-docx__overlay">
            <ViewerLoading label={t("library.viewer.loading.docxLayout")} />
          </div>
        ) : null}
        <iframe
          ref={iframeRef}
          className="viewer-docx__frame"
          title={t("library.viewer.docx.frameTitle", { name: fileName })}
          sandbox="allow-same-origin"
          srcDoc={DOCX_FRAME}
          onLoad={() => setFrameReady(true)}
        />
      </div>
    </div>
  );
}
