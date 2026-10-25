import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { useListFrequentlyUsedPrompts } from "../../generated-apis-types";

interface ChatIntroProps {
  readonly onSuggestion: (text: string) => void;
  readonly disabled?: boolean;
}

const SETTINGS_PROMPTS_HREF = "/settings#settings-frequent-prompts";

/** The empty `/chat` room before a transcript exists. */
export function ChatIntro({ onSuggestion, disabled = false }: ChatIntroProps) {
  const promptsQuery = useListFrequentlyUsedPrompts({
    query: { staleTime: 60_000 },
  });
  const prompts = promptsQuery.data?.resources ?? [];

  return (
    <section className="chat-intro">
      <span className="chat-intro__mark" aria-hidden="true">
        <Icon name="chat" size={22} />
      </span>
      <p className="eyebrow">Chat · archive desk</p>
      <h2>Ask the archive a question.</h2>
      <p className="chat-intro__description">
        Every answer keeps its tool steps, citations, and presented files in a
        persistent transcript. Start with a question, or ask the agent to open
        something from the shelves.
      </p>

      <div className="chat-intro__suggestions">
        <p className="mono-label">Frequently used prompts</p>

        {promptsQuery.isPending ? (
          <p className="chat-intro__prompts-state" role="status">
            Reading saved prompts…
          </p>
        ) : null}

        {promptsQuery.isError ? (
          <p className="chat-intro__prompts-state" role="status">
            Saved prompts are unavailable.{" "}
            <Link to={SETTINGS_PROMPTS_HREF}>Open prompt settings</Link>
          </p>
        ) : null}

        {!promptsQuery.isPending &&
        !promptsQuery.isError &&
        prompts.length === 0 ? (
          <p className="chat-intro__prompts-state">
            No frequent prompts yet.{" "}
            <Link to={SETTINGS_PROMPTS_HREF}>Add them in Settings</Link>.
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

      <p className="chat-intro__note">
        Enter sends · Shift+Enter adds a newline. The first send opens a new
        thread.
      </p>
    </section>
  );
}
