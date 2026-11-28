// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import { extractMarkdownSnippet, extractTextSnippet } from "./markdown-snippet";

test("a leading YAML frontmatter block is removed", () => {
  const source = [
    "---",
    "title: Archive notes",
    "tags: [family, 2026]",
    "---",
    "",
    "# Archive notes",
    "",
    "First paragraph.",
  ].join("\n");

  expect(extractMarkdownSnippet(source)).toBe(
    "# Archive notes\n\nFirst paragraph.",
  );
});

test("frontmatter delimited with three dots is also removed", () => {
  const source = "---\ntitle: Note\n...\nBody";
  expect(extractMarkdownSnippet(source)).toBe("Body");
});

test("CRLF and lone CR are normalized before extraction", () => {
  const source = "---\r\ntitle: Note\r\n---\r\n# Heading\r\n\r\nLine one.\rLine two.";
  expect(extractMarkdownSnippet(source)).toBe(
    "# Heading\n\nLine one.\nLine two.",
  );
});

test("truncation stops at the last complete line within the budget", () => {
  const source = "first line\nsecond line\nthird line";
  expect(extractMarkdownSnippet(source, 23)).toBe("first line\nsecond line");
  expect(extractMarkdownSnippet(source, 20)).toBe("first line");
});

test("a single long opening line is cut at the budget", () => {
  const source = "x".repeat(40);
  expect(extractMarkdownSnippet(source, 12)).toBe("x".repeat(12));
});

test("empty input and frontmatter-only files produce an empty snippet", () => {
  expect(extractMarkdownSnippet("")).toBe("");
  expect(extractMarkdownSnippet("---\ntitle: Empty\n---\n")).toBe("");
  expect(extractMarkdownSnippet("---\ntitle: Unclosed\n")).toBe(
    "---\ntitle: Unclosed",
  );
});

test("a byte-order mark before the frontmatter is ignored", () => {
  expect(extractMarkdownSnippet("\uFEFF---\ntitle: Note\n---\nBody")).toBe("Body");
});

test("plain-text snippets keep CSV headers and config keys verbatim", () => {
  expect(extractTextSnippet("name,count\r\nFamily,6\r\n")).toBe("name,count\nFamily,6\n");
  expect(extractTextSnippet("---\nkey = value\n")).toBe("---\nkey = value\n");
});

test("single-line JSON is pretty-printed, JSON Lines are left alone", () => {
  expect(extractTextSnippet('{"a":1,"b":[2]}')).toBe('{\n  "a": 1,\n  "b": [\n    2\n  ]\n}');
  expect(extractTextSnippet('{"a":1}\n{"a":2}\n')).toBe('{"a":1}\n{"a":2}\n');
});

test("long text stops at a line boundary within the budget", () => {
  const source = Array.from({ length: 200 }, (_, index) => `line ${index}`).join("\n");
  const snippet = extractTextSnippet(source, 50);
  expect(snippet.length).toBeLessThanOrEqual(50);
  expect(snippet.endsWith("\n")).toBe(false);
  expect(source.startsWith(snippet)).toBe(true);
});
