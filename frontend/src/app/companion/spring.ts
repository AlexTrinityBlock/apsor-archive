/**
 * Tiny damped-spring integrator for the marionette's sway. Semi-implicit
 * Euler is stable for the small, clamped time steps an animation frame gives.
 */

export interface SpringState {
  readonly value: number;
  readonly velocity: number;
}

export interface SpringConfig {
  readonly stiffness: number;
  readonly damping: number;
}

/** A loose pendulum: visible overshoot, settles in about a second. */
export const SWAY_SPRING: SpringConfig = { stiffness: 90, damping: 9 };
/** Firm return to the dock after a throw. */
export const DOCK_SPRING: SpringConfig = { stiffness: 170, damping: 22 };

const MAX_STEP_SECONDS = 1 / 30;

export function stepSpring(
  state: SpringState,
  target: number,
  seconds: number,
  config: SpringConfig,
): SpringState {
  let remaining = Math.max(0, seconds);
  let { value, velocity } = state;
  while (remaining > 0) {
    const dt = Math.min(MAX_STEP_SECONDS, remaining);
    const force = -config.stiffness * (value - target) - config.damping * velocity;
    velocity += force * dt;
    value += velocity * dt;
    remaining -= dt;
  }
  return { value, velocity };
}

export function isSettled(state: SpringState, target: number, epsilon = 0.05): boolean {
  return Math.abs(state.value - target) < epsilon && Math.abs(state.velocity) < epsilon;
}

/** Map horizontal drag velocity (px/ms) to a sway angle in degrees. */
export function swayForVelocity(velocityX: number, maxDegrees = 16): number {
  const angle = -velocityX * 14;
  return Math.max(-maxDegrees, Math.min(maxDegrees, angle));
}

/** Gentle breathing: vertical bob in px and a small sway in degrees. */
export function breathing(timeMs: number): { readonly bob: number; readonly sway: number } {
  const t = timeMs / 1000;
  return {
    bob: Math.sin(t * ((2 * Math.PI) / 4.2)) * 2.2,
    sway: Math.sin(t * ((2 * Math.PI) / 6.8) + 0.9) * 1.1,
  };
}
