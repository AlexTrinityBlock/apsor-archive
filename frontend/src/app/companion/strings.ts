/**
 * Marionette string geometry. The control bar hangs at the top of the stage;
 * strings run to the head anchor and both wrists, following the figure's sway.
 */

export interface StringPath {
  readonly key: "head" | "left" | "right";
  readonly d: string;
  /** Lower strings fade into the figure so approximate wrists never jar. */
  readonly fade: boolean;
}

export interface StringInput {
  readonly width: number;
  /** Distance from the stage top to the figure's top edge. */
  readonly span: number;
  readonly figureHeight: number;
  readonly anchor: { readonly x: number; readonly y: number };
  /** Figure rotation in degrees around the pivot under the bar. */
  readonly swayDegrees: number;
  /** 0 = taut, 1 = fully slack (held, sleeping). */
  readonly slack: number;
  /** Crossed, wobbling strings for the confused pose. */
  readonly tangled: boolean;
  /** Time in ms, used only for the tangle wobble. */
  readonly time: number;
}

export const BAR_Y = 12;

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

function rotate(
  x: number,
  y: number,
  pivotX: number,
  pivotY: number,
  degrees: number,
): [number, number] {
  const radians = (degrees * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const dx = x - pivotX;
  const dy = y - pivotY;
  return [pivotX + dx * cos - dy * sin, pivotY + dx * sin + dy * cos];
}

/** Bar attachment x positions: left tip, centre, right tip. */
export function barPoints(width: number): readonly [number, number, number] {
  return [width * 0.16, width * 0.5, width * 0.84];
}

export function marionetteStrings(input: StringInput): readonly StringPath[] {
  const { width, span, figureHeight, anchor, swayDegrees, slack, tangled, time } = input;
  const pivotX = width / 2;
  const pivotY = span;
  const [barLeft, barCentre, barRight] = barPoints(width);
  const headX = anchor.x * width;
  const headY = span + anchor.y * figureHeight + 2;
  const wristY = span + figureHeight * 0.36;
  const targets = {
    head: rotate(headX, headY, pivotX, pivotY, swayDegrees),
    left: rotate(width * 0.27, wristY, pivotX, pivotY, swayDegrees),
    right: rotate(width * 0.73, wristY, pivotX, pivotY, swayDegrees),
  };
  const wobble = tangled ? Math.sin(time / 140) * 5 : 0;
  const starts = {
    head: barCentre,
    left: tangled ? barRight : barLeft,
    right: tangled ? barLeft : barRight,
  };
  const sag = 4 + slack * 26;
  const keys = ["head", "left", "right"] as const;
  return keys.map((key) => {
    const [endX, endY] = targets[key];
    const startX = starts[key];
    const controlX = (startX + endX) / 2 + swayDegrees * 0.8 + (key === "head" ? 0 : wobble);
    const controlY = (BAR_Y + endY) / 2 + sag * (key === "head" ? 0.6 : 1);
    return {
      key,
      d: `M ${round(startX)} ${BAR_Y} Q ${round(controlX)} ${round(controlY)} ${round(endX)} ${round(endY)}`,
      fade: key !== "head",
    };
  });
}
