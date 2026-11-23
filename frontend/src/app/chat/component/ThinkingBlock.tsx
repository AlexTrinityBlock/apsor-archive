import { useState } from "react";

import { useI18n } from "../../i18n";

interface ThinkingBlockProps {
  /** Provider reasoning/thinking text. It is plain text, never Markdown. */
  readonly text: string;
  /** Provider-reported reasoning tokens for this step, when available. */
  readonly tokens?: number | null;
  /** Persisted steps stay collapsed; a live step may open immediately. */
  readonly defaultOpen?: boolean;
}

/** A non-interactive, scrollable trace of provider thinking. */
export function ThinkingBlock({
  text,
  tokens = null,
  defaultOpen = false,
}: ThinkingBlockProps) {
  const { t, formatNumber } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  if (text.trim().length === 0) {
    return null;
  }
  return (
    <details
      className="chat-thinking"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="chat-thinking__summary">
        <span>{t("chat.assistant.thinking")}</span>
        {tokens !== null && tokens > 0 ? (
          <span className="chat-thinking__tokens">
            {t("chat.assistant.thinkingTokens", {
              count: formatNumber(tokens),
            })}
          </span>
        ) : null}
      </summary>
      <div className="chat-thinking__body" tabIndex={0}>
        {text}
      </div>
    </details>
  );
}
