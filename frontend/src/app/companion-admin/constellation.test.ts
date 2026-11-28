// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  EMPTY_FILTER,
  asWeight,
  constellationLines,
  countTold,
  filterFragments,
  hashUnit,
  isTold,
  layoutStars,
  lineDiff,
  matchesDirectory,
  sparklinePoints,
  templatePlaceholders,
  tierForWeight,
  timelineMarks,
  weightOf,
  type FragmentLike,
} from "./constellation";

const fragment = (overrides: Partial<FragmentLike>): FragmentLike => ({
  key: "vellum-001",
  tier: "first",
  state: "unlocked",
  origin: "preset",
  text: "The lamp in the east wing.",
  themes: ["night"],
  told_count: 0,
  ...overrides,
});

describe("weights", () => {
  test("accept either the legacy tier or the new weight", () => {
    expect(weightOf({ tier: "first" })).toBe("everyday");
    expect(weightOf({ tier: "familiar" })).toBe("past");
    expect(weightOf({ tier: "rare" })).toBe("heart");
    expect(weightOf({ weight: "heart", tier: "first" })).toBe("heart");
    expect(weightOf({})).toBe("everyday");
    expect(asWeight("rare")).toBe("heart");
    expect(tierForWeight("past")).toBe("familiar");
  });

  test("told comes from the state or the count; nothing is locked", () => {
    expect(isTold({ state: "told", told_count: 0 })).toBe(true);
    expect(isTold({ state: "locked", told_count: 2 })).toBe(true);
    expect(isTold({ state: "locked", told_count: 0 })).toBe(false);
  });
});

describe("layoutStars", () => {
  const fragments = [
    fragment({ key: "a", tier: "first", state: "told", told_count: 2 }),
    fragment({ key: "b", weight: "past" }),
    fragment({ key: "c", tier: "rare", state: "locked" }),
  ];

  test("is deterministic and stays inside the square", () => {
    const first = layoutStars(fragments, 200);
    expect(layoutStars(fragments, 200)).toEqual(first);
    for (const star of first) {
      expect(star.x).toBeGreaterThanOrEqual(0);
      expect(star.x).toBeLessThanOrEqual(200);
      expect(star.y).toBeGreaterThanOrEqual(0);
      expect(star.y).toBeLessThanOrEqual(200);
    }
  });

  test("shows every memory, heavier weights on wider rings, told stars larger", () => {
    const stars = layoutStars(fragments, 200);
    expect(stars).toHaveLength(3);
    const distance = (key: string) => {
      const star = stars.find((item) => item.key === key)!;
      return Math.hypot(star.x - 100, star.y - 100);
    };
    expect(distance("a")).toBeLessThan(distance("b"));
    expect(distance("b")).toBeLessThan(distance("c"));
    expect(stars.find((star) => star.key === "a")!.r).toBeGreaterThan(
      stars.find((star) => star.key === "b")!.r,
    );
    expect(stars.find((star) => star.key === "c")!.weight).toBe("heart");
  });

  test("joins only told, visible stars", () => {
    const stars = layoutStars(
      [
        fragment({ key: "a", state: "told" }),
        fragment({ key: "b", told_count: 1 }),
        fragment({ key: "c", state: "told", hidden_by_admin: true }),
        fragment({ key: "d" }),
      ],
      100,
    );
    expect(constellationLines(stars)).toHaveLength(1);
  });

  test("hashUnit is stable and bounded", () => {
    expect(hashUnit("vellum")).toBe(hashUnit("vellum"));
    expect(hashUnit("x")).toBeGreaterThanOrEqual(0);
    expect(hashUnit("x")).toBeLessThanOrEqual(1);
  });
});

describe("filterFragments and countTold", () => {
  const items = [
    fragment({ key: "a", state: "told", themes: ["rain"] }),
    fragment({ key: "b", tier: "rare", origin: "admin" }),
    fragment({
      key: "c",
      origin: "generated",
      text: "A door opened onto a bakery.",
    }),
    fragment({ key: "d", hidden_by_admin: true }),
  ];

  test("filters by told state, weight, origin, and text", () => {
    expect(filterFragments(items, EMPTY_FILTER)).toHaveLength(4);
    expect(
      filterFragments(items, { ...EMPTY_FILTER, told: "told" }).map(
        (i) => i.key,
      ),
    ).toEqual(["a"]);
    expect(
      filterFragments(items, { ...EMPTY_FILTER, told: "untold" }).map(
        (i) => i.key,
      ),
    ).toEqual(["b", "c", "d"]);
    expect(
      filterFragments(items, { ...EMPTY_FILTER, weight: "heart" }).map(
        (i) => i.key,
      ),
    ).toEqual(["b"]);
    expect(
      filterFragments(items, { ...EMPTY_FILTER, origin: "generated" }).map(
        (i) => i.key,
      ),
    ).toEqual(["c"]);
    expect(
      filterFragments(items, { ...EMPTY_FILTER, query: "BAKERY" }).map(
        (i) => i.key,
      ),
    ).toEqual(["c"]);
    expect(
      filterFragments(items, { ...EMPTY_FILTER, query: "rain" }).map(
        (i) => i.key,
      ),
    ).toEqual(["a"]);
  });

  test("counts told and untold, skipping hidden memories", () => {
    expect(countTold(items)).toEqual({ told: 1, untold: 2, total: 3 });
  });
});

describe("timelineMarks", () => {
  test("marks the first conversation, the last and next moments, and now", () => {
    const { span, marks } = timelineMarks({
      completedRuns: 7,
      lastStoryRun: 5,
      nextMomentIn: 2,
    });
    expect(span).toBeGreaterThan(9);
    expect(marks.map((mark) => mark.kind)).toEqual([
      "start",
      "lastMoment",
      "now",
      "moment",
    ]);
    const now = marks.find((mark) => mark.kind === "now")!;
    const moment = marks.find((mark) => mark.kind === "moment")!;
    expect(moment.run).toBe(9);
    expect(moment.at).toBeGreaterThan(now.at);
    for (const mark of marks) {
      expect(mark.at).toBeGreaterThanOrEqual(0);
      expect(mark.at).toBeLessThanOrEqual(1);
    }
  });

  test("omits moments that have not happened or are switched off", () => {
    const { marks } = timelineMarks({
      completedRuns: 0,
      lastStoryRun: null,
      nextMomentIn: null,
    });
    expect(marks.map((mark) => mark.kind)).toEqual(["start", "now"]);
  });
});

describe("small helpers", () => {
  test("sparklinePoints scales to the peak", () => {
    expect(sparklinePoints([])).toBe("");
    const points = sparklinePoints([0, 2, 4], 40, 10).split(" ");
    expect(points).toHaveLength(3);
    expect(points[0]).toBe("0,9");
    expect(points[2]).toBe("40,1");
  });

  test("matchesDirectory filters by text and status", () => {
    const row = {
      username: "ada",
      display_name: "Ada L",
      role: "user",
      is_active: true,
    };
    expect(matchesDirectory(row, "ad", "all", false)).toBe(true);
    expect(matchesDirectory(row, "zz", "all", false)).toBe(false);
    expect(matchesDirectory(row, "", "root", false)).toBe(false);
    expect(matchesDirectory(row, "", "disabled", false)).toBe(false);
    expect(matchesDirectory(row, "", "companion", true)).toBe(true);
  });

  test("templatePlaceholders lists names once in order", () => {
    expect(templatePlaceholders("{a} {b} {a} {B}")).toEqual(["a", "b"]);
  });

  test("lineDiff marks additions and removals", () => {
    expect(lineDiff("a\nb\nc", "a\nc\nd")).toEqual([
      { kind: "same", text: "a" },
      { kind: "remove", text: "b" },
      { kind: "same", text: "c" },
      { kind: "add", text: "d" },
    ]);
  });
});
