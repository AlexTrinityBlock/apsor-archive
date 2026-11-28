import { Icon } from "../../component/Icon";
import type { AgentSpeakerSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { SpeakerMark } from "./SpeakerMark";

interface ReplyAuthorProps {
  /** Who said it; null when no companion was active. */
  readonly speaker: AgentSpeakerSchema | null | undefined;
  /** True while the reply is still streaming. */
  readonly live?: boolean;
}

/**
 * The author mark at the top of every assistant reply, live or saved. Both
 * states render through this one component so the header keeps its shape when
 * a streamed reply becomes a stored entry.
 */
export function ReplyAuthor({ speaker, live = false }: ReplyAuthorProps) {
  const { t } = useI18n();
  return (
    <span className="chat-turn__who">
      {live ? <span className="chat-pulse chat-turn__live-dot" aria-hidden="true" /> : null}
      {speaker ? (
        <SpeakerMark speaker={speaker} />
      ) : (
        <>
          <span className="chat-turn__mark chat-turn__mark--agent" aria-hidden="true">
            <Icon name="spark" size={11} />
          </span>
          <span>{t("chat.assistant.author")}</span>
        </>
      )}
    </span>
  );
}
