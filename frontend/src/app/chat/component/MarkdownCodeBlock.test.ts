// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";
import { createElement } from "react";

import { collectCodeText } from "./MarkdownCodeBlock";

describe("collectCodeText", () => {
  test("returns a plain string unchanged", () => {
    expect(collectCodeText("const value = 1;")).toBe("const value = 1;");
  });

  test("joins multiple text children and keeps the trailing newline", () => {
    const code = createElement(
      "code",
      { className: "language-ts" },
      "const a = 1;\n",
      "const b = 2;\n",
    );

    expect(collectCodeText(code)).toBe("const a = 1;\nconst b = 2;\n");
  });

  test("walks nested arrays and elements in order", () => {
    const tree = [
      "header\n",
      createElement("code", null, [
        createElement("span", { key: "body" }, "body"),
        "\n",
      ]),
      ["tail"],
    ];

    expect(collectCodeText(tree)).toBe("header\nbody\ntail");
  });

  test("converts numbers and ignores non-text children", () => {
    const tree = [
      123,
      null,
      undefined,
      false,
      createElement("br", { key: "break" }),
    ];

    expect(collectCodeText(tree)).toBe("123");
  });
});
