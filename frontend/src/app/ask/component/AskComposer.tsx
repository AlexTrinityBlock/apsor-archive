import { useId, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";

const RESULT_OPTIONS = Array.from({ length: 7 }, (_, index) => index + 2);

interface AskComposerProps {
  readonly question: string;
  readonly onQuestionChange: (value: string) => void;
  readonly resultNumber: number;
  readonly onResultNumberChange: (value: number) => void;
  readonly onSubmit: (question: string) => void;
  readonly pending: boolean;
}

/**
 * A sticky writing desk: plain textarea, a per-kind retrieval cap, and one
 * submit action. Cmd/Ctrl + Enter is the keyboard path.
 */
export function AskComposer({
  question,
  onQuestionChange,
  resultNumber,
  onResultNumberChange,
  onSubmit,
  pending,
}: AskComposerProps) {
  const inputId = useId();
  const hintId = useId();
  const canSubmit = question.trim().length >= 2 && !pending;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    onSubmit(question.trim());
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || (!event.metaKey && !event.ctrlKey)) {
      return;
    }
    event.preventDefault();
    if (canSubmit) {
      onSubmit(question.trim());
    }
  };

  return (
    <form
      className="ask-composer"
      onSubmit={handleSubmit}
      aria-label="Ask the archive"
    >
      <div className="ask-composer__sheet">
        <div className="ask-composer__head">
          <label className="eyebrow" htmlFor={inputId}>
            Your question
          </label>
          <span className="ask-composer__hint" id={hintId}>
            <kbd>⌘</kbd>/<kbd>Ctrl</kbd> + <kbd>Enter</kbd> to ask
          </span>
        </div>

        <textarea
          id={inputId}
          name="question"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What did the archive record about..."
          rows={3}
          maxLength={2000}
          autoComplete="off"
          aria-describedby={hintId}
        />

        <div className="ask-composer__foot">
          <label className="ask-composer__select">
            <span className="eyebrow">Sources per kind</span>
            <select
              value={resultNumber}
              onChange={(event) => onResultNumberChange(Number(event.target.value))}
              disabled={pending}
            >
              {RESULT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <div className="ask-composer__submit">
            <span className="ask-composer__note">
              Grounded by 2–4 retrieval steps.
            </span>
            <Button
              type="submit"
              variant="ink"
              size="md"
              disabled={!canSubmit}
              aria-busy={pending}
            >
              {pending ? (
                <>
                  <Loader size={16} label="Asking the archive" />
                  Asking…
                </>
              ) : (
                <>
                  <span>Ask</span>
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
