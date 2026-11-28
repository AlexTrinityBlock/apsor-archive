// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  anchoredScrollTop,
  distanceFromBottom,
  isNearBottom,
  isUnstickKey,
  isUpwardWheel,
} from "./scroll-follow";

describe("scroll follow", () => {
  test("measures the distance from the bottom", () => {
    expect(
      distanceFromBottom({ scrollHeight: 1000, scrollTop: 600, clientHeight: 300 }),
    ).toBe(100);
    expect(
      distanceFromBottom({ scrollHeight: 300, scrollTop: 0, clientHeight: 400 }),
    ).toBe(0);
  });

  test("re-sticks only close to the bottom", () => {
    expect(
      isNearBottom({ scrollHeight: 1000, scrollTop: 680, clientHeight: 300 }),
    ).toBe(true);
    expect(
      isNearBottom({ scrollHeight: 1000, scrollTop: 600, clientHeight: 300 }),
    ).toBe(false);
  });

  test("recognizes reading-upward intent", () => {
    expect(isUnstickKey("PageUp")).toBe(true);
    expect(isUnstickKey("Home")).toBe(true);
    expect(isUnstickKey("End")).toBe(false);
    expect(isUpwardWheel(-3)).toBe(true);
    expect(isUpwardWheel(4)).toBe(false);
  });

  test("keeps the reader anchored when older rows are prepended", () => {
    expect(anchoredScrollTop({ scrollHeight: 1000, scrollTop: 0 }, 1600)).toBe(600);
    expect(anchoredScrollTop({ scrollHeight: 1000, scrollTop: 250 }, 1000)).toBe(250);
  });
});
