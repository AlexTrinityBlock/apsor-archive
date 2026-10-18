import { useEffect, useId, useRef, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";

interface ChatComposerProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly pending: boolean;
  readonly streaming: boolean;
  readonly disabled?: boolean;
  readonly onStop: () => void;
}

const MAX_HEIGHT = 220;

/** A sticky correspondence desk: multiline, Cmd/Ctrl+Enter, and a stop note. */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  pending,
  streaming,
  disabled = false,
  onStop,
}: ChatComposerProps) {
  const inputId = useId();
  const hintId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSubmit = value.trim().length > 0 && !pending && !disabled;

  let note = "The transcript is persistent; citations open the viewer.";
  if (streaming) {
    note = "A run is open. Stop it to keep the completed entries.";
  } else if (disabled) {
    note = "This thread cannot accept new notes right now.";
  }

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const submit = () => {
    if (canSubmit) {
      onSubmit(value.trim());
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || (!event.metaKey && !event.ctrlKey)) {
      return;
    }
    event.preventDefault();
    submit();
  };

  return (
    <form className="chat-composer" onSubmit={handleSubmit} aria-label="Write to the archive">
      <div className="chat-composer__sheet">
        <div className="chat-composer__head">
          <label className="eyebrow" htmlFor={inputId}>
            Correspondence
          </label>
          <span className="chat-composer__hint" id={hintId}>
            <kbd>⌘</kbd>/<kbd>Ctrl</kbd> + <kbd>Enter</kbd> to send
          </span>
        </div>

        <textarea
          ref={textareaRef}
          id={inputId}
          name="message"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the archive, or ask it to open a resource..."
          rows={3}
          maxLength={32000}
          autoComplete="off"
          disabled={disabled}
          aria-describedby={hintId}
          aria-busy={pending}
        />

        <div className="chat-composer__foot">
          <span className="chat-composer__note">{note}</span>

          <div className="chat-composer__submit">
            {streaming ? (
              <Button
                type="button"
                variant="secondary"
                size="md"
                className="chat-composer__stop"
                onClick={onStop}
              >
                <Icon name="stop" size={14} />
                Stop
              </Button>
            ) : null}
            <Button
              type="submit"
              variant="ink"
              size="md"
              disabled={!canSubmit}
              aria-busy={pending}
            >
              {pending && !streaming ? (
                <>
                  <Loader size={16} label="Opening a thread" />
                  Opening…
                </>
              ) : (
                <>
                  <span>Send</span>
                  <Icon name="send" size={16} />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
