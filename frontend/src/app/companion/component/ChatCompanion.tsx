import { selectCharacter, useCompanionCatalog, useCompanionPreference } from "../api";
import type { CompanionStreamInput } from "../director";
import { useReducedMotion } from "../hook/useReducedMotion";
import { effectiveMotion } from "../preference";
import { effectiveLevel, presetForLevel } from "../size";
import { CompanionOverlay } from "./CompanionOverlay";
import "../companion.css";

interface ChatCompanionProps {
  /** The live chat stream; structurally compatible with `ChatStreamView`. */
  readonly stream: CompanionStreamInput | null;
  /** Current composer draft; typing makes the companion listen. */
  readonly draft: string;
  /** Conversation id or "new"; a change greets the reader. */
  readonly conversationKey: string;
}

/** Quiet time before a run of keyboard size steps is written to the server. */
const KEY_WRITE_DEFER_MS = 400;

/**
 * The chat page's single mount point for the companion. It reads only state
 * the page already has, so the chat workspace stays unaware of the overlay's
 * internals.
 */
export function ChatCompanion({ stream, draft, conversationKey }: ChatCompanionProps) {
  const [preference, update] = useCompanionPreference();
  const catalog = useCompanionCatalog();
  const systemReduced = useReducedMotion();
  if (!preference.enabled) {
    return null;
  }
  const character = selectCharacter(catalog, preference.companionId);
  if (character === null) {
    return null;
  }
  return (
    <CompanionOverlay
      key={character.id}
      character={character}
      motion={effectiveMotion(preference.motion, systemReduced)}
      level={effectiveLevel(preference.scale, preference.size)}
      onLevel={(level, deferred) =>
        update(
          { scale: level, size: presetForLevel(level) },
          deferred ? { deferMs: KEY_WRITE_DEFER_MS } : undefined,
        )
      }
      opacityMode={preference.opacityMode}
      stream={stream}
      draft={draft}
      conversationKey={conversationKey}
    />
  );
}
