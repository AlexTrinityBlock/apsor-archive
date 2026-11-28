// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { routeLabelKey, workspaceSegment } from "./route-title";

const routes = [
  { to: "/chat", labelKey: "chat" },
  { to: "/library", labelKey: "library" },
  { to: "/settings", labelKey: "settings" },
] as const;

describe("route title", () => {
  test("finds the owning workspace label", () => {
    expect(routeLabelKey("/chat/12", routes)).toBe("chat");
    expect(routeLabelKey("/library", routes)).toBe("library");
    expect(routeLabelKey("/settings/models", routes)).toBe("settings");
  });

  test("does not match a partial segment", () => {
    expect(routeLabelKey("/chatter", routes)).toBeNull();
  });

  test("extracts the workspace segment", () => {
    expect(workspaceSegment("/library/files/3")).toBe("library");
    expect(workspaceSegment("/")).toBe("");
  });
});
