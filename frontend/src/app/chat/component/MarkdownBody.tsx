import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { CitationChip } from "./CitationChip";
import { remarkCitations } from "./remarkCitations";
import type { CitationToken } from "../types";

const SUMMARY_HREF = /^#citation-summary-(\d+)$/;
const VIEWER_HREF = /^\/viewer\/(file|media|memory)\/(\d+)$/;

function citationFromHref(href: string): CitationToken | null {
  const summary = SUMMARY_HREF.exec(href);
  if (summary) {
    const id = Number(summary[1]);
    return Number.isSafeInteger(id) && id > 0
      ? { kind: "summary", id, chunk: null }
      : null;
  }

  if (!href.startsWith("/viewer/")) {
    return null;
  }
  try {
    const url = new URL(href, "http://localhost");
    const match = VIEWER_HREF.exec(url.pathname);
    if (!match) {
      return null;
    }
    const kind = match[1];
    if (kind !== "file" && kind !== "media" && kind !== "memory") {
      return null;
    }
    const id = Number(match[2]);
    if (!Number.isSafeInteger(id) || id <= 0) {
      return null;
    }
    const rawChunk = kind === "file" ? url.searchParams.get("chunk") : null;
    const chunk = rawChunk === null ? null : Number(rawChunk);
    return {
      kind,
      id,
      chunk:
        chunk !== null && Number.isSafeInteger(chunk) && chunk > 0 ? chunk : null,
    };
  } catch {
    return null;
  }
}

const MARKDOWN_COMPONENTS: Components = {
  a: ({ href, children }) => {
    if (!href) {
      return <span className="chat-markdown__plain-link">{children}</span>;
    }

    const citation = citationFromHref(href);
    if (citation) {
      return <CitationChip token={citation} label={children} />;
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

interface MarkdownBodyProps {
  readonly markdown: string;
}

/**
 * Renders model prose with GFM and safe citation links. Raw HTML is skipped,
 * remote images are not loaded, and only same-origin or http(s) links survive.
 */
export const MarkdownBody = memo(function MarkdownBody({
  markdown,
}: MarkdownBodyProps) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkCitations]}
        components={MARKDOWN_COMPONENTS}
        skipHtml
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
});
