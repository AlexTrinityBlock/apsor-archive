import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useI18n } from "../../i18n";

function MarkdownLink({ href, children }: ComponentProps<"a">) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  );
}

function MarkdownImage({ alt }: ComponentProps<"img">) {
  const { t } = useI18n();
  return (
    <span className="viewer-md__image">
      {t("library.viewer.markdown.imagePlaceholder", {
        alt: alt || t("library.viewer.markdown.untitled"),
      })}
    </span>
  );
}

/**
 * Markdown is rendered as React elements with raw HTML skipped. External
 * images are deliberately suppressed so opening a note never leaks a request
 * to an arbitrary host; links open in a new tab with `noopener`.
 */
export function MarkdownSheet({ content }: { readonly content: string }) {
  return (
    <div className="viewer-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{ a: MarkdownLink, img: MarkdownImage }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
