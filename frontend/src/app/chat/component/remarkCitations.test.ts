// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";
import type { Paragraph, Root } from "mdast";

import { setActiveLocale } from "../../i18n";
import { remarkCitations } from "./remarkCitations";

setActiveLocale("en");

function rootWithText(value: string): Root {
  return {
    type: "root",
    children: [
      {
        type: "paragraph",
        children: [{ type: "text", value }],
      },
    ],
  };
}

function links(tree: Root): Array<{ url: string; label: string }> {
  const paragraph = tree.children[0] as Paragraph;
  return paragraph.children.flatMap((child) => {
    if (child.type !== "link") {
      return [];
    }
    const label = child.children
      .map((item) => (item.type === "text" ? item.value : ""))
      .join("");
    return [{ url: child.url, label }];
  });
}

describe("remarkCitations", () => {
  test("converts ASCII citation tokens", () => {
    const tree = rootWithText("See [memory:7] and [file:10#2].");

    remarkCitations()(tree);

    expect(links(tree)).toEqual([
      { url: "/library/memories/7", label: "[memory:7]" },
      { url: "/library/files/10?chunk=2", label: "[file:10#2]" },
    ]);
  });

  test("converts web citation tokens to in-page anchors", () => {
    const tree = rootWithText("Per [web:w3] and ［web:w12］, not [web:w0].");

    remarkCitations()(tree);

    expect(links(tree)).toEqual([
      { url: "#citation-web-3", label: "[web:w3]" },
      { url: "#citation-web-12", label: "［web:w12］" },
    ]);
  });

  test("converts full-width citation tokens", () => {
    const tree = rootWithText("See ［memory:147］ and ［file:93］.");

    remarkCitations()(tree);

    expect(links(tree)).toEqual([
      { url: "/library/memories/147", label: "［memory:147］" },
      { url: "/library/files/93", label: "［file:93］" },
    ]);
  });
});
