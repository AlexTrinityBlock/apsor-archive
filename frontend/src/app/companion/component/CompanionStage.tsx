import { useEffect, useRef, type CSSProperties, type RefObject } from "react";

import type { CompanionAction } from "../actions";
import { useFramePlayer } from "../hook/useFramePlayer";
import type { CompanionCharacter } from "../manifest";
import type { CompanionMotion } from "../preference";
import { SWAY_SPRING, breathing, stepSpring, swayForVelocity, type SpringState } from "../spring";
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
  /** Free space above the figure for floating effects. */
  readonly span: number;
  readonly dragMotion: RefObject<DragMotion>;
  /** False while hidden or minimized; pauses the animation loop. */
  readonly active: boolean;
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
 * The free-standing figure: crossfading pose layers, a soft contact shadow,
 * and per-action effects. Sway (pivoting at the feet) and breathing run on one
 * requestAnimationFrame loop that writes CSS variables directly, so React
 * renders only when the pose changes.
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
  const figureRef = useRef<HTMLDivElement>(null);
  const layers = useFramePlayer(character, action, motion === "full");
  const animated = motion === "full";
  const tilt = restingTilt(action);

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
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animated, active, action, tilt, dragMotion, motion]);

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
