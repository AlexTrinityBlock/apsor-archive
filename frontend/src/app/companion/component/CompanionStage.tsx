import { useEffect, useId, useMemo, useRef, type CSSProperties, type RefObject } from "react";

import type { CompanionAction } from "../actions";
import { useFramePlayer } from "../hook/useFramePlayer";
import type { CompanionCharacter } from "../manifest";
import type { CompanionMotion } from "../preference";
import { SWAY_SPRING, breathing, stepSpring, swayForVelocity, type SpringState } from "../spring";
import { BAR_Y, barPoints, marionetteStrings } from "../strings";
import { CompanionEffects } from "./CompanionEffects";

/** Live drag input shared by the overlay without re-rendering the stage. */
export interface DragMotion {
  /** Horizontal pointer velocity in px/ms while dragging, else 0. */
  vx: number;
}

interface CompanionStageProps {
  readonly character: CompanionCharacter;
  readonly action: CompanionAction;
  readonly motion: CompanionMotion;
  readonly width: number;
  readonly figureHeight: number;
  readonly span: number;
  readonly dragMotion: RefObject<DragMotion>;
  /** False while hidden or minimized; pauses the animation loop. */
  readonly active: boolean;
}

function slackFor(action: CompanionAction): number {
  switch (action) {
    case "held":
      return 1;
    case "sleeping":
      return 0.75;
    case "confused":
      return 0.35;
    case "success":
    case "greet":
      return 0.05;
    default:
      return 0.15;
  }
}

/** Per-action resting tilt so poses read even without art changes. */
function restingTilt(action: CompanionAction): number {
  switch (action) {
    case "listening":
      return -3;
    case "thinking":
      return 2.5;
    case "sleeping":
      return 6;
    case "confused":
      return -5;
    default:
      return 0;
  }
}

/**
 * The marionette itself: a control bar, three strings, the crossfading pose
 * layers, and per-action effects. Sway and breathing run on one
 * requestAnimationFrame loop that writes CSS variables and string paths
 * directly, so React renders only when the pose changes.
 */
export function CompanionStage({
  character,
  action,
  motion,
  width,
  figureHeight,
  span,
  dragMotion,
  active,
}: CompanionStageProps) {
  const gradientId = useId().replace(/:/g, "");
  const figureRef = useRef<HTMLDivElement>(null);
  const pathRefs = useRef<(SVGPathElement | null)[]>([]);
  const layers = useFramePlayer(character, action, motion === "full");
  const animated = motion === "full";
  const height = span + figureHeight;
  const slack = slackFor(action);
  const tangled = action === "confused";
  const tilt = restingTilt(action);

  const staticStrings = useMemo(
    () =>
      marionetteStrings({
        width,
        span,
        figureHeight,
        anchor: character.anchor,
        swayDegrees: motion === "off" ? 0 : tilt,
        slack,
        tangled,
        time: 0,
      }),
    [width, span, figureHeight, character.anchor, motion, tilt, slack, tangled],
  );

  useEffect(() => {
    const figure = figureRef.current;
    if (!animated || !active || figure === null) {
      figure?.style.setProperty("--companion-sway", `${motion === "off" ? 0 : tilt}deg`);
      figure?.style.setProperty("--companion-bob", "0px");
      return undefined;
    }
    let frame = 0;
    let last = performance.now();
    let sway: SpringState = { value: tilt, velocity: 0 };
    const tick = (now: number) => {
      const seconds = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (document.visibilityState === "visible") {
        const breath = breathing(now);
        const dragSway = swayForVelocity(dragMotion.current?.vx ?? 0);
        const target = tilt + dragSway + (action === "held" ? 0 : breath.sway);
        sway = stepSpring(sway, target, seconds, SWAY_SPRING);
        const bob = action === "held" || action === "sleeping" ? 0 : breath.bob;
        figure.style.setProperty("--companion-sway", `${sway.value.toFixed(2)}deg`);
        figure.style.setProperty("--companion-bob", `${bob.toFixed(2)}px`);
        const strings = marionetteStrings({
          width,
          span,
          figureHeight,
          anchor: character.anchor,
          swayDegrees: sway.value,
          slack,
          tangled,
          time: now,
        });
        strings.forEach((item, index) => {
          pathRefs.current[index]?.setAttribute("d", item.d);
        });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animated, active, action, tilt, slack, tangled, width, span, figureHeight, character.anchor, dragMotion, motion]);

  const [barLeft, barCentre, barRight] = barPoints(width);
  const style = {
    "--companion-accent": character.accent,
    "--companion-span": `${span}px`,
    "--companion-figure-h": `${figureHeight}px`,
  } as CSSProperties;

  return (
    <div
      className={`companion-stage is-${action}${animated ? " is-animated" : ""}`}
      style={style}
      data-motion={motion}
    >
      <svg
        className="companion-rig"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <linearGradient
            id={`${gradientId}-fade`}
            gradientUnits="userSpaceOnUse"
            x1="0"
            y1={BAR_Y}
            x2="0"
            y2={span + figureHeight * 0.4}
          >
            <stop offset="0" stopColor="currentColor" stopOpacity="0.85" />
            <stop offset="0.7" stopColor="currentColor" stopOpacity="0.5" />
            <stop offset="1" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g className="companion-rig__strings">
          {staticStrings.map((item, index) => (
            <path
              key={item.key}
              ref={(node) => {
                pathRefs.current[index] = node;
              }}
              d={item.d}
              className={`companion-rig__string companion-rig__string--${item.key}`}
              stroke={item.fade ? `url(#${gradientId}-fade)` : undefined}
            />
          ))}
        </g>
        <g className="companion-rig__bar">
          <line
            className="companion-rig__handle"
            x1={barCentre}
            y1={2}
            x2={barCentre}
            y2={BAR_Y + 6}
          />
          <rect
            className="companion-rig__beam"
            x={barLeft - 5}
            y={BAR_Y - 2.5}
            width={barRight - barLeft + 10}
            height={5}
            rx={2.5}
          />
          <rect
            className="companion-rig__cross"
            x={barCentre - width * 0.11}
            y={BAR_Y + 4}
            width={width * 0.22}
            height={3.5}
            rx={1.75}
          />
          {[barLeft, barCentre, barRight].map((x) => (
            <circle key={x} className="companion-rig__cap" cx={x} cy={BAR_Y} r={3.2} />
          ))}
        </g>
      </svg>
      <div
        className="companion-figure"
        ref={figureRef}
        style={{ width, height: figureHeight, top: span }}
      >
        <div className="companion-figure__glow" aria-hidden="true" />
        <div className="companion-figure__body">
          {layers.map((layer) => (
            <img
              key={layer.key}
              className={`companion-figure__pose${layer.leaving ? " is-leaving" : " is-entering"}`}
              src={layer.src}
              alt=""
              width={width}
              height={figureHeight}
              draggable={false}
              decoding="async"
            />
          ))}
        </div>
        {animated && active ? <CompanionEffects action={action} /> : null}
      </div>
    </div>
  );
}
