import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { useListFrequentlyUsedPrompts } from "../../generated-apis-types";
import { useI18n } from "../../i18n";

interface ChatIntroProps {
  readonly onSuggestion: (text: string) => void;
  readonly disabled?: boolean;
}

const SETTINGS_PROMPTS_HREF = "/settings#settings-frequent-prompts";

/** The empty `/chat` room before a transcript exists. */
export function ChatIntro({ onSuggestion, disabled = false }: ChatIntroProps) {
  const { t } = useI18n();
  const promptsQuery = useListFrequentlyUsedPrompts({
    query: { staleTime: 60_000 },
  });
  const prompts = promptsQuery.data?.resources ?? [];

  return (
    <section className="chat-intro">
      <span className="chat-intro__mark" aria-hidden="true">
        <Icon name="chat" size={22} />
      </span>
      <p className="eyebrow">{t("chat.intro.eyebrow")}</p>
      <h2>{t("chat.intro.title")}</h2>
      <p className="chat-intro__description">{t("chat.intro.description")}</p>

      <div className="chat-intro__suggestions">
        <p className="mono-label">{t("chat.intro.promptsLabel")}</p>

        {promptsQuery.isPending ? (
          <p className="chat-intro__prompts-state" role="status">
            {t("chat.intro.promptsReading")}
          </p>
        ) : null}

        {promptsQuery.isError ? (
          <p className="chat-intro__prompts-state" role="status">
            {t("chat.intro.promptsUnavailable")}{" "}
            <Link to={SETTINGS_PROMPTS_HREF}>
              {t("chat.intro.openPromptSettings")}
            </Link>
          </p>
        ) : null}

        {!promptsQuery.isPending &&
        !promptsQuery.isError &&
        prompts.length === 0 ? (
          <p className="chat-intro__prompts-state">
            {t("chat.intro.promptsEmpty")}{" "}
            <Link to={SETTINGS_PROMPTS_HREF}>
              {t("chat.intro.addPrompts")}
            </Link>
          </p>
        ) : null}

        {prompts.map((prompt) => (
          <button
            key={prompt.id}
            type="button"
            className="chat-intro__suggestion"
            onClick={() => onSuggestion(prompt.prompt_text)}
            disabled={disabled}
          >
            <span className="chat-intro__suggestion-copy">
              <span className="chat-intro__suggestion-title">
                {prompt.title}
              </span>
              <span className="chat-intro__suggestion-preview">
                {prompt.prompt_text}
              </span>
            </span>
            <Icon name="arrow-right" size={14} />
          </button>
        ))}
      </div>

      <p className="chat-intro__note">{t("chat.intro.note")}</p>
    </section>
  );
}
