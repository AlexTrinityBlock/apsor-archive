import { isValidElement, useMemo, type ReactNode } from "react";

import { CopyButton } from "../../component/CopyButton";
import { useI18n } from "../../i18n";

/**
 * Collects the visible text of a rendered markdown code block.
 *
 * The markdown pipeline skips raw HTML and runs no syntax highlighter, so the
 * tree contains only strings and React elements. Reading the React children
 * keeps the copy source identical to what is displayed without touching the
 * DOM.
 *
 * @param node - Rendered `pre` or `code` children.
 * @returns Concatenated text content.
 */
export function collectCodeText(node: ReactNode): string {
  if (typeof node === "string") {
    return node;
  }
  if (typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map((child) => collectCodeText(child)).join("");
  }
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return collectCodeText(node.props.children);
  }
  return "";
}

function copyableCodeText(node: ReactNode): string {
  const text = collectCodeText(node);
  return text.endsWith("\n") ? text.slice(0, -1) : text;
}

interface MarkdownCodeBlockProps {
  readonly children?: ReactNode;
}

/**
 * Renders a fenced code block with a persistent copy control.
 *
 * The control sits in a slim row above the `pre`, so it never scrolls away with
 * long lines and never covers the code. The copied value is the raw code text
 * only: language classes and the generated trailing newline stay out.
 */
export function MarkdownCodeBlock({ children }: MarkdownCodeBlockProps) {
  const { t } = useI18n();
  const value = useMemo(() => copyableCodeText(children), [children]);

  return (
    <div className="chat-code-block">
      <div className="chat-code-block__bar">
        <CopyButton
          value={value}
          label={t("chat.markdown.copyCode")}
          title={t("chat.markdown.copyCodeTitle")}
          className="chat-code-block__copy"
          iconOnly
        />
      </div>
      <pre>{children}</pre>
    </div>
  );
}
