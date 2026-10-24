import { Icon } from "../../component/Icon";

interface ChatIntroProps {
  readonly onSuggestion: (text: string) => void;
  readonly disabled?: boolean;
}

const SUGGESTIONS: ReadonlyArray<string> = [
  "What does the archive hold about the Qing court?",
  "Open a file from the library and summarise its key claims.",
  "Trace the lineage of the most recent memory and explain what changed.",
];

/** The empty `/chat` room before a transcript exists. */
export function ChatIntro({ onSuggestion, disabled = false }: ChatIntroProps) {
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
        <p className="mono-label">Suggested prompts</p>
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="chat-intro__suggestion"
            onClick={() => onSuggestion(suggestion)}
            disabled={disabled}
          >
            <span>{suggestion}</span>
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
