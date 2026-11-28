/** Characters kept from a Markdown original for its library thumbnail. */
export const MARKDOWN_SNIPPET_CHARS = 900;

function stripFrontmatter(source: string): string {
  const lines = source.split("\n");
  if (lines[0]?.trim() !== "---") {
    return source;
  }

  for (let index = 1; index < lines.length; index += 1) {
    const marker = lines[index].trim();
    if (marker === "---" || marker === "...") {
      return lines.slice(index + 1).join("\n");
    }
  }
  return source;
}

/**
 * Extract the readable beginning of a Markdown document.
 *
 * A leading YAML frontmatter block is removed, CRLF and lone CR are normalized
 * to LF, and the result stops at the last line boundary within the character
 * budget so a thumbnail never starts in the middle of a sentence. When the
 * opening line is longer than the whole budget, it is cut at the budget
 * instead of returning an empty snippet.
 */
export function extractMarkdownSnippet(
  source: string,
  maxChars: number = MARKDOWN_SNIPPET_CHARS,
): string {
  if (source.length === 0 || maxChars <= 0) {
    return "";
  }

  const normalized = source
    .replace(/^\uFEFF/, "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
  const body = stripFrontmatter(normalized).replace(/^\n+/, "");
  if (body.length <= maxChars) {
    return body.trimEnd();
  }

  const boundary = body.lastIndexOf("\n", maxChars);
  const end = boundary > 0 ? boundary : maxChars;
  return body.slice(0, end).trimEnd();
}

/** Characters kept from a plain-text original (CSV, JSON, logs) for its card. */
export const TEXT_SNIPPET_CHARS = 600;

/**
 * The first lines of a plain-text original, normalized like Markdown but with
 * nothing stripped: CSV headers, JSON braces and config keys are the content.
 * Single-line JSON is pretty-printed so the card shows structure, not one row.
 */
export function extractTextSnippet(source: string, maxChars: number = TEXT_SNIPPET_CHARS): string {
  let text = source.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const trimmed = text.trim();
  if ((trimmed.startsWith("{") || trimmed.startsWith("[")) && !trimmed.slice(0, 2000).includes("\n")) {
    try {
      text = JSON.stringify(JSON.parse(trimmed), null, 2);
    } catch {
      // Not one JSON value (e.g. JSON Lines); keep the source as written.
    }
  }
  if (text.length <= maxChars) {
    return text;
  }
  const cut = text.lastIndexOf("\n", maxChars);
  return text.slice(0, cut > 0 ? cut : maxChars);
}
