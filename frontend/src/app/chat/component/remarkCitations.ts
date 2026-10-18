/**
 * Turns `[file:10#2]`, `[memory:7]`, and `[media:4]` text into ordinary
 * Markdown link nodes before rendering. Code, existing links, and images are
 * left untouched, so the transform cannot create nested links.
 */
import type { Parent, PhrasingContent, Root, RootContent, Text } from "mdast";

import { citationHref, citationLabel, parseCitationLabel } from "../types";

// Literal alternatives plus one digit run: linear, but flagged heuristically.
// eslint-disable-next-line security/detect-unsafe-regex
const CITATION = /\[(?:file|memory|media|summary):\d+(?:#\d+)?\]/g;
const SKIP = new Set([
  "link",
  "linkReference",
  "image",
  "imageReference",
  "inlineCode",
  "code",
  "html",
]);

function splitText(node: Text): PhrasingContent[] {
  const pieces: PhrasingContent[] = [];
  let cursor = 0;

  for (const match of node.value.matchAll(CITATION)) {
    const start = match.index;
    if (start === undefined) {
      continue;
    }
    const label = match[0];
    const token = parseCitationLabel(label);
    if (!token) {
      continue;
    }
    if (start > cursor) {
      pieces.push({ type: "text", value: node.value.slice(cursor, start) });
    }
    pieces.push({
      type: "link",
      url: citationHref(token) ?? `#citation-summary-${token.id}`,
      title: `Archive citation ${citationLabel(token)}`,
      children: [{ type: "text", value: label }],
    });
    cursor = start + label.length;
  }

  if (cursor < node.value.length) {
    pieces.push({ type: "text", value: node.value.slice(cursor) });
  }
  return pieces.length > 0 ? pieces : [node];
}

function transform(parent: Parent): void {
  const next: RootContent[] = [];
  for (const child of parent.children) {
    if (child.type === "text") {
      next.push(...splitText(child));
      continue;
    }
    if ("children" in child && !SKIP.has(child.type)) {
      transform(child as Parent);
    }
    next.push(child);
  }
  parent.children = next;
}

/** The remark transformer; mounted once per Markdown render. */
export function remarkCitations(): (tree: Root) => void {
  return (tree) => {
    transform(tree);
  };
}
