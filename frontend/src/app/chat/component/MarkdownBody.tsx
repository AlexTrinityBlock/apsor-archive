import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { CitationChip } from "./CitationChip";
import { remarkCitations } from "./remarkCitations";
import type { CitationToken } from "../types";

const SUMMARY_HREF = /^#citation-summary-(\d+)$/;
const MEMORY_HREF = /^\/memory\/(\d+)\/?$/;
const VIEWER_HREF = /^\/viewer\/(file|memory)\/(\d+)\/?$/;

function positiveId(value: string | null): number | null {
  if (value === null) {
    return null;
  }
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function citationFromHref(href: string): CitationToken | null {
  const summary = SUMMARY_HREF.exec(href);
  if (summary) {
    const id = positiveId(summary[1]);
    return id === null ? null : { kind: "summary", id, chunk: null };
  }

  try {
    const url = new URL(href, "http://localhost");

    if (url.pathname === "/library") {
      const id = positiveId(url.searchParams.get("file"));
      if (id === null) {
        return null;
      }
      return {
        kind: "file",
        id,
        chunk: positiveId(url.searchParams.get("chunk")),
      };
    }

    const memory = MEMORY_HREF.exec(url.pathname);
    if (memory) {
      const id = positiveId(memory[1]);
      return id === null ? null : { kind: "memory", id, chunk: null };
    }

    const viewer = VIEWER_HREF.exec(url.pathname);
    if (viewer) {
      const id = positiveId(viewer[2]);
      if (id === null) {
        return null;
      }
      if (viewer[1] === "memory") {
        return { kind: "memory", id, chunk: null };
      }
      return {
        kind: "file",
        id,
        chunk: positiveId(url.searchParams.get("chunk")),
      };
    }
  } catch {
    return null;
  }
  return null;
}

function buildComponents(
  onOpenCitation: ((token: CitationToken) => void) | undefined,
  memoryTitles: ReadonlyMap<number, string>,
): Components {
  return {
    a: ({ href, children }) => {
      if (!href) {
        return <span className="chat-markdown__plain-link">{children}</span>;
      }

      const citation = citationFromHref(href);
      if (citation) {
        return (
          <CitationChip
            token={citation}
            label={children}
            memoryTitle={
              citation.kind === "memory"
                ? memoryTitles.get(citation.id)
                : undefined
            }
            onOpen={onOpenCitation}
          />
        );
      }

      if (href.startsWith("#")) {
        return (
          <a className="chat-markdown__link" href={href}>
            {children}
          </a>
        );
      }

      if (href.startsWith("/") && !href.startsWith("//")) {
        return (
          <Link className="chat-markdown__link" to={href}>
            {children}
          </Link>
        );
      }

      if (/^https?:\/\//i.test(href)) {
        return (
          <a
            className="chat-markdown__link"
            href={href}
            target="_blank"
            rel="noreferrer noopener"
          >
            {children}
          </a>
        );
      }

      return <span className="chat-markdown__plain-link">{children}</span>;
    },
    img: ({ alt }) => (
      <span className="chat-markdown__image-note">
        Image omitted from the transcript{alt ? `: ${alt}` : ""}
      </span>
    ),
    table: ({ children }) => (
      <div className="chat-markdown__table">
        <table>{children}</table>
      </div>
    ),
  };
}

interface MarkdownBodyProps {
  readonly markdown: string;
  readonly memoryTitles?: ReadonlyMap<number, string>;
  readonly onOpenCitation?: (token: CitationToken) => void;
}

const NO_MEMORY_TITLES: ReadonlyMap<number, string> = new Map();

/**
 * Renders model prose with GFM and safe citation links. Raw HTML is skipped,
 * remote images are not loaded, and only same-origin or http(s) links survive.
 */
export const MarkdownBody = memo(function MarkdownBody({
  markdown,
  memoryTitles = NO_MEMORY_TITLES,
  onOpenCitation,
}: MarkdownBodyProps) {
  const components = useMemo(
    () => buildComponents(onOpenCitation, memoryTitles),
    [memoryTitles, onOpenCitation],
  );

  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkCitations]}
        components={components}
        skipHtml
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
});
