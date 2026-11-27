// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { EMPTY_DRAFTS, draftKey, readDraft, writeDraft } from "./draft-map";

describe("draft map", () => {
  test("keeps one draft per conversation", () => {
    let drafts = writeDraft(EMPTY_DRAFTS, draftKey(4), "first");
    drafts = writeDraft(drafts, draftKey(null), "unsaved");
    expect(readDraft(drafts, draftKey(4))).toBe("first");
    expect(readDraft(drafts, "new")).toBe("unsaved");
    expect(readDraft(drafts, draftKey(9))).toBe("");
  });

  test("an empty draft removes the entry", () => {
    const drafts = writeDraft(writeDraft(EMPTY_DRAFTS, "4", "text"), "4", "");
    expect("4" in drafts).toBe(false);
  });

  test("an unchanged write returns the same record", () => {
    const drafts = writeDraft(EMPTY_DRAFTS, "4", "text");
    expect(writeDraft(drafts, "4", "text")).toBe(drafts);
  });
});
