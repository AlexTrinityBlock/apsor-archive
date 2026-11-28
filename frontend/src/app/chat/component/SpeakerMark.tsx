import { companionIdFromRef, selectCharacter, useCompanionCatalog } from "../../companion/api";
import type { AgentSpeakerSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";

interface SpeakerMarkProps {
  readonly speaker: AgentSpeakerSchema;
}

/**
 * The librarian who said an assistant step: a small portrait and her name.
 * Speakers can change mid-conversation when the person switches companion, so
 * every step shows who said it rather than the conversation's first companion.
 */
export function SpeakerMark({ speaker }: SpeakerMarkProps) {
  const { t } = useI18n();
  const catalog = useCompanionCatalog();
  const character = selectCharacter(catalog, companionIdFromRef(speaker.ref));
  const name = speaker.name || character?.name || speaker.ref;
  return (
    <span className="chat-turn__speaker" title={t("chat.assistant.saidBy", { name })}>
      {character?.portrait ? (
        <img
          className="chat-turn__speaker-portrait"
          src={character.portrait}
          alt=""
          width={17}
          height={17}
          decoding="async"
          style={{ borderColor: character.accent }}
        />
      ) : null}
      <span className="chat-turn__speaker-name">{name}</span>
    </span>
  );
}
