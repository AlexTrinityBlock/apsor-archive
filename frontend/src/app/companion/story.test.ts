// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  THEMES_MAX,
  addTheme,
  groupLoreByTier,
  loreSnippet,
  parseLoreFragment,
  splitHeardAndOwn,
  readSurfacedLore,
  validateLore,
  type LoreFragment,
} from "./story";

describe("parseLoreFragment", () => {
  test("reads API rows and drops incomplete ones", () => {
    expect(
      parseLoreFragment({
        id: 7,
        text: "I once mended a ledger.",
        themes: ["ledgers", 3],
        tier: "first",
        is_default: true,
      }),
    ).toEqual({
      id: "7",
      tier: "first",
      text: "I once mended a ledger.",
      themes: ["ledgers"],
      isDefault: true,
      edited: false,
      own: false,
      heard: false,
    });
    expect(parseLoreFragment({ tier: "rare", text: "t" })).toBeNull();
    expect(parseLoreFragment({ id: "x", tier: "rare" })).toBeNull();
    expect(parseLoreFragment({ id: "y", tier: "epic", text: "t" })?.tier).toBe("familiar");
  });
});

describe("groupLoreByTier", () => {
  test("keeps tier order and drops empty tiers", () => {
    const fragment = (id: string, tier: LoreFragment["tier"]): LoreFragment => ({
      id,
      tier,
      text: id,
      themes: [],
      isDefault: true,
      edited: false,
      own: false,
      heard: false,
    });
    expect(
      groupLoreByTier([fragment("a", "rare"), fragment("b", "first"), fragment("c", "first")]).map(
        (group) => [group.tier, group.fragments.map((item) => item.id)],
      ),
    ).toEqual([
      ["first", ["b", "c"]],
      ["rare", ["a"]],
    ]);
  });
});

describe("splitHeardAndOwn", () => {
  const row = (id: string, extra: Record<string, unknown>) =>
    parseLoreFragment({ id, text: id, tier: "first", ...extra })!;

  test("shows heard and own memories only, never untold ones", () => {
    const split = splitHeardAndOwn([
      row("heard", { heard: true }),
      row("told-count", { told_count: 2 }),
      row("untold", {}),
      row("mine", { own: true }),
      row("edited", { edited: true, heard: true }),
    ]);
    expect(split.heard.map((item) => item.id)).toEqual(["heard", "told-count"]);
    expect(split.own.map((item) => item.id)).toEqual(["mine", "edited"]);
  });
});

describe("themes and validation", () => {
  test("addTheme normalizes, dedupes, and caps", () => {
    expect(addTheme([], "  old   maps ")).toEqual(["old maps"]);
    expect(addTheme(["Maps"], "maps")).toEqual(["Maps"]);
    expect(addTheme([], "   ")).toEqual([]);
    const full = Array.from({ length: THEMES_MAX }, (_, i) => `t${i}`);
    expect(addTheme(full, "new")).toBe(full);
  });

  test("validateLore", () => {
    expect(validateLore({ text: "  ", themes: [], tier: "first" })).toBe("empty");
    expect(validateLore({ text: "x".repeat(2001), themes: [], tier: "first" })).toBe("tooLong");
    expect(validateLore({ text: "ok", themes: [], tier: "rare" })).toBeNull();
  });
});

describe("surfaced lore", () => {
  test("reads at most three valid items from tool data", () => {
    expect(readSurfacedLore(null)).toEqual([]);
    expect(
      readSurfacedLore({
        results: [],
        lore: [
          { id: 1, text: " A " },
          { id: 2 },
          { text: "no id" },
          { id: 3, text: "B" },
          { id: 4, text: "C" },
          { id: 5, text: "D" },
        ],
      }),
    ).toEqual([
      { id: "1", text: "A" },
      { id: "3", text: "B" },
      { id: "4", text: "C" },
    ]);
  });

  test("snippets cut at a word boundary", () => {
    expect(loreSnippet("short text")).toBe("short text");
    const snippet = loreSnippet("word ".repeat(100), 40);
    expect(snippet.endsWith("…")).toBe(true);
    expect(snippet.length).toBeLessThanOrEqual(41);
  });
});
