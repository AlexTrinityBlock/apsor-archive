import { selectCharacter, useCompanionCatalog, useCompanionPreference } from "../api";
import type { CompanionStreamInput } from "../director";
import { useReducedMotion } from "../hook/useReducedMotion";
import { effectiveMotion } from "../preference";
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

/**
 * The chat page's single mount point for the companion. It reads only state
 * the page already has, so the chat workspace stays unaware of the overlay's
 * internals.
 */
export function ChatCompanion({ stream, draft, conversationKey }: ChatCompanionProps) {
  const [preference] = useCompanionPreference();
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
      stream={stream}
      draft={draft}
      conversationKey={conversationKey}
    />
  );
}
