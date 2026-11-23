import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { useElementWidth } from "../../../viewer/component/useElementWidth";
import { fetchViewerText, fileContentUrl } from "../../../viewer/component/viewer-utils";
import { extractMarkdownSnippet } from "./markdown-snippet";
import {
  getMarkdownSnippet,
  setMarkdownSnippet,
  setMarkdownSnippetFailed,
} from "./markdown-snippet-cache";

// The page is laid out at a fixed width with normal reading typography, then
// the whole page is scaled down. This keeps headings, lists, and code blocks
// proportional instead of shrinking every font independently.
const MARKDOWN_PAGE_WIDTH = 320;

type SnippetState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly text: string }
  | { readonly kind: "failed" };

function initialState(cacheKey: string): SnippetState {
  const cached = getMarkdownSnippet(cacheKey);
  if (cached === undefined) {
    return { kind: "loading" };
  }
  return cached.kind === "text"
    ? { kind: "ready", text: cached.text }
    : { kind: "failed" };
}

interface MarkdownThumbProps {
  readonly fileId: number;
  readonly cacheKey: string;
  readonly onFailure: () => void;
}

/**
 * A real Markdown page, cropped to the library card stage.
 *
 * The snippet is fetched only after the card approaches the viewport (the
 * caller mounts this component then), and only the first 900 characters are
 * rendered. Raw HTML is skipped, remote images are suppressed, and links are
 * plain text so a decorative thumbnail can never navigate. The page is scaled
 * from a fixed 320px layout and continues past a bottom fade.
 */
export function MarkdownThumb({ fileId, cacheKey, onFailure }: MarkdownThumbProps) {
  const [setHostElement, hostWidth] = useElementWidth<HTMLSpanElement>();
  const [state, setState] = useState<SnippetState>(() => initialState(cacheKey));
  const onFailureRef = useRef(onFailure);

  useEffect(() => {
    onFailureRef.current = onFailure;
  }, [onFailure]);

  useEffect(() => {
    if (state.kind === "failed") {
      onFailureRef.current();
      return;
    }
    if (state.kind === "ready") {
      return;
    }

    const controller = new AbortController();
    let disposed = false;

    fetchViewerText(fileContentUrl(fileId), controller.signal).then(
      (source) => {
        if (disposed) {
          return;
        }
        const text = extractMarkdownSnippet(source);
        setMarkdownSnippet(cacheKey, text);
        setState({ kind: "ready", text });
      },
      () => {
        if (disposed || controller.signal.aborted) {
          return;
        }
        setMarkdownSnippetFailed(cacheKey);
        setState({ kind: "failed" });
      },
    );

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [cacheKey, fileId, state.kind]);

  const ready = state.kind === "ready";
  const scale = hostWidth > 0 ? hostWidth / MARKDOWN_PAGE_WIDTH : 0;
  // A ready snippet still waits one frame for the width observer; a failed
  // snippet is replaced by the parent's type tile, so neither may keep a
  // spinner on screen.
  const busy = state.kind === "loading" || (ready && scale <= 0);

  return (
    <span ref={setHostElement} className="library-thumb__markdown" aria-hidden="true">
      {ready && scale > 0 ? (
        <>
          <span
            className="library-thumb__markdown-page"
            style={{
              width: `${MARKDOWN_PAGE_WIDTH}px`,
              transform: `scale(${scale})`,
            }}
          >
            <span className="library-markdown-thumb">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkBreaks]}
                skipHtml
                components={{
                  a: ({ children }) => (
                    <span className="library-markdown-thumb__link">{children}</span>
                  ),
                  img: () => null,
                }}
              >
                {state.text}
              </ReactMarkdown>
            </span>
          </span>
          <span className="library-thumb__markdown-fade" />
        </>
      ) : (
        <>
          <span className="library-thumb__paper library-thumb__paper--overlay" />
          {busy ? (
            <span className="library-thumb__spinner" aria-hidden="true" />
          ) : null}
        </>
      )}
    </span>
  );
}
