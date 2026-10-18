import { Icon, type IconName } from "../../component/Icon";

interface ChatIntroProps {
  readonly onSuggestion: (text: string) => void;
  readonly disabled?: boolean;
}

const SUGGESTIONS: ReadonlyArray<{ text: string; label: string }> = [
  {
    text: "What did the archive record about the Qing dynasty?",
    label: "Search the shelves",
  },
  {
    text: "Open the file about the Qing court and tell me what matters in it.",
    label: "Present a resource",
  },
  {
    text: "Trace the lineage of the latest memory and explain what changed.",
    label: "Read a memory trace",
  },
];

const FACTS: ReadonlyArray<{ icon: IconName; title: string; note: string }> = [
  {
    icon: "history",
    title: "Persistent sheets",
    note: "Every note and answer stays in an append-only transcript.",
  },
  {
    icon: "quote",
    title: "Grounded citations",
    note: "File, memory, and media labels open the in-app viewer.",
  },
  {
    icon: "layers",
    title: "Structured tools",
    note: "Tool calls and presented resources become field-note cards.",
  },
];

/** The empty `/chat` room before a transcript exists. */
export function ChatIntro({ onSuggestion, disabled = false }: ChatIntroProps) {
  return (
    <section className="chat-intro reveal reveal-2">
      <span className="chat-intro__icon" aria-hidden="true">
        <Icon name="chat" size={26} />
      </span>
      <p className="eyebrow">Studio · correspondence desk</p>
      <h2>A thread that keeps its sources.</h2>
      <p className="chat-intro__description">
        This is the archive&apos;s long-form desk. Unlike a quick answer, a thread
        keeps every marginalia, tool step, citation, and presented resource in
        one durable reading sheet. Start with a question, or ask the agent to
        open something from the shelves.
      </p>

      <ul className="chat-intro__facts">
        {FACTS.map((fact) => (
          <li key={fact.title}>
            <span className="chat-intro__fact-icon" aria-hidden="true">
              <Icon name={fact.icon} size={16} />
            </span>
            <span>
              <strong>{fact.title}</strong>
              <span>{fact.note}</span>
            </span>
          </li>
        ))}
      </ul>

      <div className="chat-intro__suggestions">
        <p className="chat-intro__suggestions-label">Open with</p>
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.label}
            type="button"
            className="chat-intro__suggestion"
            onClick={() => onSuggestion(suggestion.text)}
            disabled={disabled}
          >
            <span>
              <span className="chat-intro__suggestion-label">
                {suggestion.label}
              </span>
              <span className="chat-intro__suggestion-text">
                {suggestion.text}
              </span>
            </span>
            <Icon name="arrow-right" size={15} />
          </button>
        ))}
      </div>

      <p className="chat-intro__note">
        The first send opens a new thread and freezes the prompt and tool set for
        its lifetime. Nothing is saved to memories unless you ask.
      </p>
    </section>
  );
}
