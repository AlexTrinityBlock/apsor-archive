import { useEffect, useMemo, useState } from "react";

import type { CompanionAction } from "../actions";
import { decodeFrames, preloadFrames } from "../frame-cache";
import {
  frameAtStep,
  likelyNextActions,
  resolveClip,
  type CompanionCharacter,
  type ResolvedClip,
} from "../manifest";

export interface FrameLayer {
  readonly key: string;
  readonly src: string;
  readonly leaving: boolean;
}

interface Display {
  readonly clip: ResolvedClip | null;
  readonly clipKey: string;
  /** Playback step; `frameAtStep` maps it to a frame (wrap or pingpong). */
  readonly step: number;
  readonly leaving: { readonly key: string; readonly src: string } | null;
}

const CROSSFADE_MS = 260;

function clipKey(characterId: string, clip: ResolvedClip): string {
  return `${characterId}:${clip.action}:${clip.frames.join("|")}`;
}

/**
 * Play the clip for an action: decode first, then crossfade from the previous
 * pose. Multi-frame clips advance at the manifest fps unless motion is off.
 */
export function useFramePlayer(
  character: CompanionCharacter,
  action: CompanionAction,
  animateFrames: boolean,
): readonly FrameLayer[] {
  const clip = useMemo(() => resolveClip(character, action), [character, action]);
  const key = clipKey(character.id, clip);
  const [display, setDisplay] = useState<Display>({
    clip: null,
    clipKey: "",
    step: 0,
    leaving: null,
  });

  useEffect(() => {
    let cancelled = false;
    decodeFrames(clip.frames)
      .catch(() => undefined)
      .then(() => {
        if (cancelled) {
          return;
        }
        setDisplay((current) => {
          if (current.clipKey === key) {
            return current;
          }
          const outgoing =
            current.clip === null
              ? null
              : {
                  key: `${current.clipKey}#${current.step}`,
                  src:
                    current.clip.frames[frameAtStep(current.clip, current.step)] ??
                    current.clip.frames[0] ??
                    "",
                };
          return { clip, clipKey: key, step: 0, leaving: outgoing };
        });
      });
    for (const next of likelyNextActions(clip.action)) {
      preloadFrames(resolveClip(character, next).frames);
    }
    return () => {
      cancelled = true;
    };
  }, [character, clip, key]);

  useEffect(() => {
    if (display.leaving === null) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setDisplay((current) => ({ ...current, leaving: null }));
    }, CROSSFADE_MS);
    return () => window.clearTimeout(timer);
  }, [display.leaving]);

  const shown = display.clip;
  const frameCount = shown?.frames.length ?? 0;
  const fps = shown?.fps ?? 0;
  const loop = shown?.loop ?? true;
  const pingpong = shown?.pingpong ?? false;
  useEffect(() => {
    if (!animateFrames || frameCount < 2 || fps <= 0) {
      return undefined;
    }
    // A finite clip stops after one pass (there and back for pingpong).
    let lastStep = Number.POSITIVE_INFINITY;
    if (!loop) {
      lastStep = pingpong ? frameCount * 2 - 2 : frameCount - 1;
    }
    const timer = window.setInterval(() => {
      setDisplay((current) =>
        current.step >= lastStep ? current : { ...current, step: current.step + 1 },
      );
    }, 1000 / fps);
    return () => window.clearInterval(timer);
  }, [animateFrames, frameCount, fps, loop, pingpong, display.clipKey]);

  const layers: FrameLayer[] = [];
  if (display.leaving !== null) {
    layers.push({ ...display.leaving, leaving: true });
  }
  if (shown !== null) {
    layers.push({
      key: display.clipKey,
      src: shown.frames[animateFrames ? frameAtStep(shown, display.step) : 0] ?? shown.frames[0] ?? "",
      leaving: false,
    });
  }
  return layers;
}
