// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { expect, test } from "bun:test";

import {
  isKeyboardOpen,
  KEYBOARD_CLOSE_INSET,
  KEYBOARD_OPEN_INSET,
  type VisualViewportMetrics,
} from "./useVisualViewport";

/** A portrait phone at rest: the visual and layout viewports agree. */
const REST: VisualViewportMetrics = {
  layoutHeight: 844,
  visualHeight: 844,
  visualTop: 0,
  scale: 1,
};

test("a resting viewport is not a keyboard", () => {
  expect(isKeyboardOpen(false, REST)).toBe(false);
});

test("an expanded URL bar does not look like a keyboard", () => {
  const urlBar: VisualViewportMetrics = {
    ...REST,
    layoutHeight: 844,
    visualHeight: 744,
  };
  expect(isKeyboardOpen(false, urlBar)).toBe(false);
});

test("a covered band at the open threshold enters the keyboard state", () => {
  const keyboard: VisualViewportMetrics = {
    ...REST,
    visualHeight: REST.layoutHeight - KEYBOARD_OPEN_INSET,
  };
  expect(isKeyboardOpen(false, keyboard)).toBe(true);
});

test("a keyboard keeps the state until the band drops below the close threshold", () => {
  const settling: VisualViewportMetrics = {
    ...REST,
    visualHeight: REST.layoutHeight - KEYBOARD_CLOSE_INSET,
  };
  expect(isKeyboardOpen(true, settling)).toBe(true);
  expect(
    isKeyboardOpen(true, {
      ...settling,
      visualHeight: REST.layoutHeight - KEYBOARD_CLOSE_INSET + 1,
    }),
  ).toBe(false);
});

test("a landscape keyboard of 130 px opens and a 90 px band stays open", () => {
  expect(
    isKeyboardOpen(false, {
      ...REST,
      visualHeight: REST.layoutHeight - 130,
    }),
  ).toBe(true);
  expect(
    isKeyboardOpen(true, {
      ...REST,
      visualHeight: REST.layoutHeight - 90,
    }),
  ).toBe(true);
});

test("a Safari-panned visual viewport is a keyboard signal", () => {
  expect(
    isKeyboardOpen(false, {
      ...REST,
      visualHeight: 720,
      visualTop: 160,
    }),
  ).toBe(true);
});

test("pinch zoom is not a keyboard", () => {
  expect(
    isKeyboardOpen(false, {
      layoutHeight: 844,
      visualHeight: 422,
      visualTop: 200,
      scale: 2,
    }),
  ).toBe(false);
});

test("missing viewport measurements never open the keyboard state", () => {
  expect(
    isKeyboardOpen(false, {
      layoutHeight: 0,
      visualHeight: Number.NaN,
      visualTop: 0,
      scale: 1,
    }),
  ).toBe(false);
});
