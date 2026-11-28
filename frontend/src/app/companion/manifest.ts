/**
 * Companion character manifests: parsing untrusted JSON (preset files or a
 * server response) into a typed character and resolving action frames.
 */
import {
  ACTION_FALLBACKS,
  COMPANION_ACTIONS,
  type CompanionAction,
} from "./actions";

export type CompanionGender = "female" | "male" | "unspecified";

export interface CompanionActionClip {
  /** Absolute or same-origin URLs, already resolved against the base. */
  readonly frames: readonly string[];
  /** Frames per second; 0 means a single still pose. */
  readonly fps: number;
  readonly loop: boolean;
  /** Play forward then backward (1-2-3-2-1…) instead of wrapping. */
  readonly pingpong: boolean;
}

export interface CompanionCharacter {
  readonly id: string;
  readonly name: string;
  readonly gender: CompanionGender;
  readonly accent: string;
  readonly width: number;
  readonly height: number;
  readonly portrait: string | null;
  readonly actions: Readonly<Partial<Record<CompanionAction, CompanionActionClip>>>;
}

export interface CompanionPresetRef {
  readonly id: string;
  readonly name: string | null;
  readonly gender: CompanionGender;
}

type JsonObject = Readonly<Record<string, unknown>>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const SAFE_ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const SAFE_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const DEFAULT_ACCENT = "#b8933f";
const MAX_FRAMES = 24;
const MAX_FPS = 24;

export function isSafeCompanionId(value: unknown): value is string {
  return typeof value === "string" && SAFE_ID.test(value);
}

function readGender(value: unknown): CompanionGender {
  return value === "female" || value === "male" ? value : "unspecified";
}

function positiveInt(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isInteger(value) && value > 0 && value <= 4096
    ? value
    : fallback;
}

/**
 * Resolve one frame reference. Relative file names must be plain names inside
 * the character directory; absolute same-origin API paths are allowed for
 * server-hosted custom frames. Anything else is rejected.
 */
export function resolveFrameUrl(base: string, frame: unknown): string | null {
  if (typeof frame !== "string") {
    return null;
  }
  if (SAFE_FILE.test(frame) && !frame.includes("..")) {
    return `${base.replace(/\/$/, "")}/${frame}`;
  }
  if (frame.startsWith("/api/") && !frame.includes("..") && !frame.includes("//")) {
    return frame;
  }
  if (frame.startsWith("blob:")) {
    return frame;
  }
  return null;
}

function readClip(base: string, value: unknown): CompanionActionClip | null {
  if (!isObject(value) || !Array.isArray(value.frames)) {
    return null;
  }
  const frames = value.frames
    .slice(0, MAX_FRAMES)
    .map((frame) => resolveFrameUrl(base, frame))
    .filter((frame): frame is string => frame !== null);
  if (frames.length === 0) {
    return null;
  }
  const fps =
    typeof value.fps === "number" && Number.isFinite(value.fps)
      ? Math.min(MAX_FPS, Math.max(0, value.fps))
      : 0;
  const animated = frames.length > 1;
  return {
    frames,
    fps: animated ? fps || 6 : 0,
    loop: value.loop !== false,
    pingpong: animated && value.pingpong === true,
  };
}

/**
 * Parse a manifest. Returns null when the manifest has no usable `idle` pose,
 * because every fallback chain ends there.
 */
export function parseManifest(
  value: unknown,
  base: string,
): CompanionCharacter | null {
  if (!isObject(value) || !isSafeCompanionId(value.id)) {
    return null;
  }
  const actions: Partial<Record<CompanionAction, CompanionActionClip>> = {};
  if (isObject(value.actions)) {
    for (const action of COMPANION_ACTIONS) {
      const clip = readClip(base, value.actions[action]);
      if (clip !== null) {
        actions[action] = clip;
      }
    }
  }
  if (actions.idle === undefined) {
    return null;
  }
  const size = isObject(value.size) ? value.size : {};
  const palette = isObject(value.palette) ? value.palette : {};
  const accent =
    typeof palette.accent === "string" && HEX_COLOR.test(palette.accent)
      ? palette.accent
      : DEFAULT_ACCENT;
  const name =
    typeof value.name === "string" && value.name.trim().length > 0
      ? value.name.trim().slice(0, 40)
      : value.id;
  return {
    id: value.id,
    name,
    gender: readGender(value.gender),
    accent,
    width: positiveInt(size.width, 384),
    height: positiveInt(size.height, 576),
    // Frame and portrait extensions come from the manifest (AVIF or WebP);
    // only a missing portrait falls back to the conventional AVIF name.
    portrait: resolveFrameUrl(base, value.portrait ?? "portrait.avif") ?? null,
    actions,
  };
}

/**
 * Parse the preset index. Accepts `["id", …]`, `{presets: […]}`, or
 * `{characters: […]}` whose items are ids or `{id, name, gender}` objects.
 */
export function parsePresetIndex(value: unknown): readonly CompanionPresetRef[] {
  let items: readonly unknown[] = [];
  if (Array.isArray(value)) {
    items = value;
  } else if (isObject(value)) {
    if (Array.isArray(value.presets)) {
      items = value.presets;
    } else if (Array.isArray(value.characters)) {
      items = value.characters;
    }
  }
  const seen = new Set<string>();
  const refs: CompanionPresetRef[] = [];
  for (const item of items) {
    const id = isObject(item) ? item.id : item;
    if (!isSafeCompanionId(id) || seen.has(id)) {
      continue;
    }
    seen.add(id);
    refs.push({
      id,
      name: isObject(item) && typeof item.name === "string" ? item.name : null,
      gender: isObject(item) ? readGender(item.gender) : "unspecified",
    });
  }
  return refs;
}

export interface ResolvedClip extends CompanionActionClip {
  readonly action: CompanionAction;
}

/** The clip to play for an action, walking the fallback chain to `idle`. */
export function resolveClip(
  character: CompanionCharacter,
  action: CompanionAction,
): ResolvedClip {
  for (const candidate of [action, ...ACTION_FALLBACKS[action], "idle" as const]) {
    const clip = character.actions[candidate];
    if (clip !== undefined) {
      return { ...clip, action: candidate };
    }
  }
  // parseManifest guarantees idle; this keeps the type total.
  return { frames: [], fps: 0, loop: true, pingpong: false, action: "idle" };
}

/** Every distinct frame URL a character needs, idle first. */
/**
 * Frame to show at a given playback step. Pingpong clips bounce between the
 * ends without repeating them; non-looping clips hold the last frame.
 */
export function frameAtStep(clip: CompanionActionClip, step: number): number {
  const count = clip.frames.length;
  if (count < 2 || step <= 0) {
    return 0;
  }
  if (clip.pingpong) {
    const period = count * 2 - 2;
    if (!clip.loop && step >= period) {
      return 0;
    }
    const phase = step % period;
    return phase < count ? phase : period - phase;
  }
  if (!clip.loop) {
    return Math.min(step, count - 1);
  }
  return step % count;
}

export function characterFrameUrls(character: CompanionCharacter): string[] {
  const urls = new Set<string>();
  for (const action of COMPANION_ACTIONS) {
    for (const frame of character.actions[action]?.frames ?? []) {
      urls.add(frame);
    }
  }
  return [...urls];
}

/** Frames worth decoding ahead of time for a given current action. */
export function likelyNextActions(action: CompanionAction): readonly CompanionAction[] {
  switch (action) {
    case "idle":
    case "listening":
    case "greet":
      return ["thinking", "listening", "searching"];
    case "thinking":
      return ["searching", "reading", "speaking"];
    case "searching":
    case "reading":
      return ["reading", "speaking", "presenting"];
    case "speaking":
      return ["success", "thinking"];
    default:
      return ["idle", "success"];
  }
}
