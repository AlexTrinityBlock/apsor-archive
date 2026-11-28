import {
  companionRef,
  selectCharacter,
  useCompanionCatalog,
  useCompanionPreference,
} from "../../companion/api";
import type { AgentSpeakerSchema } from "../../generated-apis-types/schemas";

/**
 * The librarian who is answering right now, before the reply is saved.
 *
 * A live turn has no stored `speaker` yet, so it shows the account's active
 * companion: the same choice the server resolves for the next message, which
 * is also the one a mid-conversation switch hands over to. Null means the
 * companion is turned off and the plain archive assistant is answering.
 */
export function useLiveSpeaker(): AgentSpeakerSchema | null {
  const [preference] = useCompanionPreference();
  const catalog = useCompanionCatalog();
  if (!preference.enabled) {
    return null;
  }
  const character = selectCharacter(catalog, preference.companionId);
  if (character === null) {
    return null;
  }
  return { ref: companionRef(character), name: character.name };
}
