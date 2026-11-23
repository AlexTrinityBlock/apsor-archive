import { useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";

import { useElementWidth } from "../../../viewer/component/useElementWidth";
import {
  DOCX_FRAME,
  DOCX_OPTIONS,
  hardenFrame,
} from "../../../viewer/component/docx-config";
import { fetchViewerBinary, fileContentUrl } from "../../../viewer/component/viewer-utils";
import { schedule } from "./render-queue";

// A4 at 96 dpi. The frame lays out at this fixed page width and the stage
// scales the whole frame down, so the visible thumbnail is the real first page
// rather than a reflowed excerpt.
const DOCX_PAGE_WIDTH = 794;
const DOCX_PAGE_HEIGHT = 1123;

// `docx-preview` draws a gray wrapper with 30px padding around the page. The
// thumbnail needs a clean white page tile, so a final style in the frame head
// removes that chrome after the render.
const DOCX_THUMB_STYLE = `
html, body { background: #ffffff; overflow: hidden; }
.docx-wrapper { background: #ffffff; padding: 0; display: block; }
.docx-wrapper > section.docx { box-shadow: none; margin: 0; }
`;

type Phase = "skeleton" | "framing" | "done" | "failed";

interface DocxThumbProps {
  readonly fileId: number;
  readonly fileName: string;
  readonly onFailure: () => void;
}

function fail(
  phaseSetter: (phase: Phase) => void,
  onFailure: () => void,
): void {
  phaseSetter("failed");
  onFailure();
}

/**
 * The first page of a DOCX original, rendered inside a sandboxed iframe.
 *
 * The iframe only allows same-origin document access so the parent can run
 * `docx-preview`; scripts remain disabled by the sandbox and are stripped
 * again by `hardenFrame`. Work starts once the stage has a measurable width
 * and the render queue grants a slot. The frame stays mounted after success,
 * so scrolling back to the card does not parse the package again.
 */
export function DocxThumb({ fileId, fileName, onFailure }: DocxThumbProps) {
  const [setHostElement, hostWidth] = useElementWidth<HTMLSpanElement>();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const renderStartedRef = useRef(false);
  const aliveRef = useRef(true);
  const onFailureRef = useRef(onFailure);
  const [started, setStarted] = useState(false);
  const [phase, setPhase] = useState<Phase>("skeleton");
  const [binary, setBinary] = useState<ArrayBuffer | null>(null);
  const [frameReady, setFrameReady] = useState(false);

  useEffect(() => {
    onFailureRef.current = onFailure;
  }, [onFailure]);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // Fetch once the mounted card has a width. Until the binary arrives, an
  // effect replay (StrictMode) or a width refinement may cancel and restart
  // the queued job; after success this effect no longer schedules anything.
  useEffect(() => {
    if (started || hostWidth <= 0) {
      return;
    }
    const controller = new AbortController();

    schedule(async (signal) => {
      const data = await fetchViewerBinary(fileContentUrl(fileId), signal);
      signal.throwIfAborted();
      return data;
    }, controller.signal).then(
      (data) => {
        if (controller.signal.aborted || !aliveRef.current) {
          return;
        }
        setBinary(data);
        setStarted(true);
        setPhase("framing");
      },
      () => {
        if (controller.signal.aborted || !aliveRef.current) {
          return;
        }
        fail(setPhase, onFailureRef.current);
      },
    );

    return () => controller.abort();
  }, [fileId, hostWidth, started]);

  // The package and the iframe are both ready. The parse itself goes through
  // the same queue as PDF and PPTX drawing, so at most two document renders
  // are ever in flight. The frame stays mounted after success.
  useEffect(() => {
    if (binary === null || !frameReady || renderStartedRef.current) {
      return;
    }
    renderStartedRef.current = true;
    const frameDocument = iframeRef.current?.contentDocument;
    if (!frameDocument) {
      fail(setPhase, onFailureRef.current);
      return;
    }

    const source = binary.slice(0);
    schedule(async () => {
      await renderAsync(source, frameDocument.body, frameDocument.head, {
        ...DOCX_OPTIONS,
      });
    }).then(
      () => {
        if (!aliveRef.current) {
          return;
        }
        hardenFrame(frameDocument);
        const style = frameDocument.createElement("style");
        style.textContent = DOCX_THUMB_STYLE;
        frameDocument.head.appendChild(style);
        setPhase("done");
      },
      () => {
        if (!aliveRef.current) {
          return;
        }
        fail(setPhase, onFailureRef.current);
      },
    );
  }, [binary, frameReady]);

  const showFrame = hostWidth > 0 && phase !== "skeleton" && phase !== "failed";

  return (
    <span ref={setHostElement} className="library-thumb__docx" aria-hidden="true">
      {showFrame ? (
        <iframe
          ref={iframeRef}
          className="library-thumb__docx-frame"
          title={fileName}
          sandbox="allow-same-origin"
          srcDoc={DOCX_FRAME}
          tabIndex={-1}
          onLoad={() => setFrameReady(true)}
          style={{
            width: `${DOCX_PAGE_WIDTH}px`,
            height: `${DOCX_PAGE_HEIGHT}px`,
            transform: `scale(${hostWidth / DOCX_PAGE_WIDTH})`,
          }}
        />
      ) : null}
      {phase !== "done" && phase !== "failed" ? (
        <span className="library-thumb__paper library-thumb__paper--overlay" />
      ) : null}
    </span>
  );
}
