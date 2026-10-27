/**
 * String operations for the Markdown toolbar.
 *
 * This module deliberately stays away from React, the DOM, and i18n: the inputs
 * are a raw string and a selection, and the output is an edit that can be applied
 * to a textarea, which makes it easy to reason about and test on its own.
 */

export type MarkdownAction =
  | "bold"
  | "italic"
  | "h1"
  | "h2"
  | "h3"
  | "quote"
  | "code"
  | "list"
  | "task"
  | "link"
  | "table";

export interface MarkdownEditSelection {
  readonly start: number;
  readonly end: number;
}

export interface MarkdownEdit {
  /**
   * The buffer range this edit replaces. Most actions replace the selection; the
   * actions that prefix each line start at the beginning of the cursor's line, so
   * `from` is not necessarily `start`.
   */
  readonly from: number;
  readonly to: number;
  /** The text that replaces `[from, to)`. */
  readonly text: string;
  /** The selection that should remain after the edit is applied. */
  readonly selection: MarkdownEditSelection;
}

export interface MarkdownActionLabels {
  readonly boldPlaceholder: string;
  readonly italicPlaceholder: string;
  readonly codePlaceholder: string;
  readonly linkPlaceholder: string;
  readonly tableColumnPlaceholder: string;
  readonly tableCellPlaceholder: string;
}

/** Build an edit that replaces the selection directly. */
function replace(
  start: number,
  end: number,
  text: string,
  selection: MarkdownEditSelection,
): MarkdownEdit {
  return { from: start, to: end, text, selection };
}

/** Wrap the selection in `marker`; with no selection, insert the placeholder and select it. */
function wrap(
  value: string,
  start: number,
  end: number,
  marker: string,
  placeholder: string,
): MarkdownEdit {
  const body = value.slice(start, end);
  if (body === "") {
    return replace(start, end, `${marker}${placeholder}${marker}`, {
      start: start + marker.length,
      end: start + marker.length + placeholder.length,
    });
  }
  return replace(start, end, `${marker}${body}${marker}`, {
    start: start + marker.length,
    end: start + marker.length + body.length,
  });
}

/** Find the start of the line containing `start`; position 0 is simply the first line start. */
function lineStartAt(value: string, start: number): number {
  if (start <= 0) {
    return 0;
  }
  return value.lastIndexOf("\n", start - 1) + 1;
}

/**
 * Add `prefix` to the start of every line the selection touches.
 *
 * This is a single contiguous replacement covering the affected line span: from
 * the start of the cursor's line to the end of the selection. It never extends
 * past the selection, so text after the cursor on the last line stays untouched.
 */
function prefixLines(
  value: string,
  start: number,
  end: number,
  prefix: string,
): MarkdownEdit {
  const lineStart = lineStartAt(value, start);
  const span = value.slice(lineStart, end);

  const prefixed = span
    .split("\n")
    .map((line) => `${prefix}${line}`)
    .join("\n");

  // span always starts at a line start, so the covered line count is the newline
  // count plus one, and every line gained a prefix.
  const lineCount = span.split("\n").length;
  const added = prefix.length * lineCount;
  return {
    from: lineStart,
    to: end,
    text: prefixed,
    selection: { start: start + prefix.length, end: end + added },
  };
}

/**
 * Block-style edit: insert multi-line content at the start of the cursor's line,
 * adding a blank line first when needed so Markdown treats it as a separate block.
 */
function block(value: string, start: number, inner: string): MarkdownEdit {
  const lineStart = lineStartAt(value, start);
  const before = value.slice(0, lineStart);
  const leading = before === "" || before.endsWith("\n\n") ? "" : "\n";
  const text = `${leading}${inner}\n`;
  return {
    from: lineStart,
    to: lineStart,
    text,
    selection: { start: lineStart + text.length, end: lineStart + text.length },
  };
}

/**
 * Apply one toolbar action to the `[start, end)` selection of `value`.
 * Every placeholder comes in through `labels`; the module itself contains no
 * locale-specific strings.
 */
export function applyMarkdownAction(
  action: MarkdownAction,
  value: string,
  start: number,
  end: number,
  labels: MarkdownActionLabels,
): MarkdownEdit {
  switch (action) {
    case "bold":
      return wrap(value, start, end, "**", labels.boldPlaceholder);
    case "italic":
      return wrap(value, start, end, "*", labels.italicPlaceholder);
    case "h1":
      return prefixLines(value, start, end, "# ");
    case "h2":
      return prefixLines(value, start, end, "## ");
    case "h3":
      return prefixLines(value, start, end, "### ");
    case "quote":
      return prefixLines(value, start, end, "> ");
    case "list":
      return prefixLines(value, start, end, "- ");
    case "task":
      return prefixLines(value, start, end, "- [ ] ");
    case "code": {
      const body = value.slice(start, end);
      if (body.includes("\n") || body === "") {
        return block(
          value,
          start,
          `\`\`\`\n${body || labels.codePlaceholder}\n\`\`\``,
        );
      }
      return wrap(value, start, end, "`", labels.codePlaceholder);
    }
    case "link": {
      const body = value.slice(start, end);
      const linkLabel = body === "" ? labels.linkPlaceholder : body;
      const text = `[${linkLabel}](https://)`;
      // Select the URL part so the user can type the address directly.
      return replace(start, end, text, {
        start: start + linkLabel.length + 3,
        end: start + text.length - 1,
      });
    }
    case "table":
      return block(
        value,
        start,
        [
          `| ${labels.tableColumnPlaceholder} | ${labels.tableColumnPlaceholder} |`,
          "| --- | --- |",
          `| ${labels.tableCellPlaceholder} | ${labels.tableCellPlaceholder} |`,
        ].join("\n"),
      );
  }
}
