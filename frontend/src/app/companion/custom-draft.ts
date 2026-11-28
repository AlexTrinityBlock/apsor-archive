/**
 * Pure helpers for the custom-companion editor: file validation, frame list
 * edits, and turning a draft into a previewable character.
 */
import { COMPANION_ACTIONS, type CompanionAction } from "./actions";
import type { CompanionActionClip, CompanionCharacter, CompanionGender } from "./manifest";

export const MAX_FRAMES_PER_ACTION = 12;
export const MAX_FRAME_BYTES = 4 * 1024 * 1024;
export const ACCEPTED_FRAME_TYPES = [
  "image/png",
  "image/webp",
  "image/avif",
  "image/jpeg",
] as const;
export const DEFAULT_DRAFT_FPS = 6;

export interface DraftFrame {
  readonly id: string;
  readonly file: File;
  /** Object URL owned by the editor; revoked when the frame leaves. */
  readonly url: string;
}

export interface DraftAction {
  readonly frames: readonly DraftFrame[];
  readonly fps: number;
}

export type DraftActions = Readonly<Partial<Record<CompanionAction, DraftAction>>>;

export type FrameRejection =
  | { readonly kind: "type"; readonly file: string }
  | { readonly kind: "size"; readonly file: string }
  | { readonly kind: "count" };

export function isAcceptedFrame(file: Pick<File, "type">): boolean {
  return (ACCEPTED_FRAME_TYPES as readonly string[]).includes(file.type);
}

/** Split incoming files into accepted ones and reasons for the rest. */
export function screenFrames(
  files: readonly File[],
  existing: number,
): { readonly accepted: readonly File[]; readonly rejected: readonly FrameRejection[] } {
  const accepted: File[] = [];
  const rejected: FrameRejection[] = [];
  for (const file of files) {
    if (!isAcceptedFrame(file)) {
      rejected.push({ kind: "type", file: file.name });
    } else if (file.size > MAX_FRAME_BYTES) {
      rejected.push({ kind: "size", file: file.name });
    } else if (existing + accepted.length >= MAX_FRAMES_PER_ACTION) {
      if (!rejected.some((item) => item.kind === "count")) {
        rejected.push({ kind: "count" });
      }
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}

/** Move one frame one step; out-of-range moves are no-ops. */
export function moveFrame<T>(frames: readonly T[], index: number, delta: -1 | 1): readonly T[] {
  const target = index + delta;
  if (index < 0 || index >= frames.length || target < 0 || target >= frames.length) {
    return frames;
  }
  const next = [...frames];
  const [item] = next.splice(index, 1);
  next.splice(target, 0, item);
  return next;
}

/** A character built from object URLs, for the live preview. */
export function draftCharacter(
  name: string,
  gender: CompanionGender,
  actions: DraftActions,
): CompanionCharacter | null {
  const idle = actions.idle;
  if (idle === undefined || idle.frames.length === 0) {
    return null;
  }
  const clips: Partial<Record<CompanionAction, CompanionActionClip>> = {};
  for (const action of COMPANION_ACTIONS) {
    const draft = actions[action];
    if (draft !== undefined && draft.frames.length > 0) {
      const multi = draft.frames.length > 1;
      clips[action] = {
        frames: draft.frames.map((frame) => frame.url),
        fps: multi ? draft.fps : 0,
        loop: true,
        pingpong: false,
      };
    }
  }
  return {
    id: "custom-draft",
    name: name.trim() || "—",
    gender,
    accent: "#b8933f",
    anchor: { x: 0.5, y: 0.04 },
    width: 384,
    height: 576,
    portrait: idle.frames[0]?.url ?? null,
    actions: clips,
  };
}

export function draftFrameCount(actions: DraftActions): number {
  return COMPANION_ACTIONS.reduce((total, action) => total + (actions[action]?.frames.length ?? 0), 0);
}
