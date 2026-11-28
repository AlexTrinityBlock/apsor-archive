// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";
// @ts-expect-error -- Node built-ins are provided by the Bun runtime; the frontend tsconfig does not load @types/node.
import { readFileSync } from "node:fs";

/**
 * pptxviewjs 1.1.9 matched slide placeholders to layout/master placeholders by
 * type only, so a slide body (`<p:ph idx="1"/>`, type "obj") never inherited the
 * master body geometry and was drawn under the title. The local patch matches
 * by idx first and treats body/obj as interchangeable; this guards that the
 * patched build is what the app bundles.
 */
describe("pptxviewjs placeholder patch", () => {
  const dist = readFileSync(
    new URL("../../node_modules/pptxviewjs/dist/PptxViewJS.es.js", import.meta.url),
    "utf8",
  );

  test("matches placeholders by idx with body/obj equivalence", () => {
    expect(dist).toContain("OOXML inheritance key");
    expect(dist).toContain("same idx; body and obj");
  });

  test("package.json registers the patch", () => {
    const pkg = JSON.parse(
      readFileSync(new URL("../../package.json", import.meta.url), "utf8"),
    ) as { patchedDependencies?: Record<string, string> };
    expect(pkg.patchedDependencies?.["pptxviewjs@1.1.9"]).toBe(
      "patches/pptxviewjs@1.1.9.patch",
    );
  });
});
