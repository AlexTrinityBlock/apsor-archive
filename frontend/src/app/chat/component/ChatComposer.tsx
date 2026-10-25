import {
  useEffect,
  useId,
  useRef,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useI18n } from "../../i18n";

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

/** A sticky composer: Enter sends, Shift+Enter inserts a newline. */
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
  const { t } = useI18n();
  const canSubmit = value.trim().length > 0 && !pending && !disabled;

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
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    ) {
      return;
    }
    event.preventDefault();
    submit();
  };

  let note = t("chat.composer.note");
  if (streaming) {
    note = t("chat.composer.noteStreaming");
  } else if (disabled) {
    note = t("chat.composer.noteDisabled");
  }

  return (
    <form
      className="chat-composer"
      onSubmit={handleSubmit}
      aria-label={t("chat.composer.formAria")}
    >
      <div className="chat-composer__box">
        <label className="visually-hidden" htmlFor={inputId}>
          {t("chat.composer.message")}
        </label>
        <textarea
          ref={textareaRef}
          id={inputId}
          name="message"
          className="chat-composer__input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("chat.composer.placeholder")}
          rows={2}
          maxLength={32000}
          autoComplete="off"
          disabled={disabled}
          aria-describedby={hintId}
          aria-busy={pending}
        />

        <div className="chat-composer__foot">
          <span className="chat-composer__note" id={hintId}>
            <span>{t("chat.composer.enterHint")}</span>
            <span className="chat-composer__state">{note}</span>
          </span>

          <div className="chat-composer__actions">
            {streaming ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="chat-composer__stop"
                onClick={onStop}
              >
                <Icon name="stop" size={13} />
                {t("chat.composer.stop")}
              </Button>
            ) : null}
            <Button
              type="submit"
              variant="ink"
              size="sm"
              disabled={!canSubmit}
              aria-busy={pending}
            >
              {pending && !streaming ? (
                <>
                  <Loader size={14} label={t("chat.composer.openingLabel")} />
                  {t("chat.composer.opening")}
                </>
              ) : (
                <>
                  <span>{t("chat.composer.send")}</span>
                  <Icon name="send" size={14} />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
