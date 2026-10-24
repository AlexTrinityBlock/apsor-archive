import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { useScrollLock } from "../../hook/useScrollLock";
import { formatNumber } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const QUESTION_MAX_CHARS = 32_000;

interface QuestionDialogProps {
  readonly mode: "create" | "edit";
  readonly initialQuestion: string;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (question: string) => void;
}

/** A focus-trapped dialog for writing or editing one saved question. */
export function QuestionDialog({
  mode,
  initialQuestion,
  saving,
  error,
  onClose,
  onSubmit,
}: QuestionDialogProps) {
  const titleId = useId();
  const helpId = useId();
  const errorId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const [draft, setDraft] = useState(initialQuestion);

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const initial =
      dialog?.querySelector<HTMLElement>("[data-autofocus]") ??
      dialog?.querySelector<HTMLElement>(FOCUSABLE) ??
      dialog;
    initial?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!saving) {
          event.preventDefault();
          onCloseRef.current();
        }
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [saving]);

  const trimmed = draft.trim();
  const description =
    mode === "create"
      ? "Saving stores the question only; no answer is generated until you run it in Chat."
      : "Saving changed text clears the stored answer and conversation link.";
  const describedBy = error ? `${helpId} ${errorId}` : helpId;
  let submitLabel = mode === "create" ? "Save question" : "Save changes";
  if (saving) {
    submitLabel = "Saving…";
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (trimmed.length === 0 || saving) {
      return;
    }
    onSubmit(trimmed);
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  return (
    <div
      className="modal"
      onMouseDown={(event) => {
        if (!saving && event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={describedBy}
        aria-busy={saving}
        tabIndex={-1}
        className="modal-dialog modal-dialog--sm question-dialog"
      >
        <header className="modal-head question-dialog__head">
          <div className="question-dialog__heading">
            <p className="eyebrow">
              {mode === "create" ? "Save question" : "Edit question"}
            </p>
            <h2 className="modal-title" id={titleId}>
              {mode === "create" ? "Keep a question for later." : "Revise this question."}
            </h2>
          </div>
          <button
            type="button"
            className="modal-btn-close"
            onClick={onClose}
            disabled={saving}
            aria-label="Close dialog"
          >
            <Icon name="close" size={18} />
          </button>
        </header>

        <form className="question-dialog__form" onSubmit={submit}>
          <div className="modal-body question-dialog__body">
            <div className="field">
              <label className="field-label" htmlFor={`${titleId}-question`}>
                Question
              </label>
              <textarea
                id={`${titleId}-question`}
                className="textarea question-dialog__textarea"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleKeyDown}
                rows={5}
                maxLength={QUESTION_MAX_CHARS}
                placeholder="What should the archive answer later?"
                autoComplete="off"
                disabled={saving}
                data-autofocus
                aria-describedby={describedBy}
              />
              <div className="question-dialog__meta">
                <p className="field-help" id={helpId}>
                  {description}
                </p>
                <span className="question-dialog__count" aria-hidden="true">
                  {formatNumber(draft.length)} / {formatNumber(QUESTION_MAX_CHARS)}
                </span>
              </div>
            </div>

            {error ? (
              <p className="question-dialog__error" id={errorId} role="alert">
                <Icon name="info" size={14} />
                <span>{error}</span>
              </p>
            ) : null}
          </div>

          <footer className="modal-actions">
            <Button
              type="button"
              variant="ghost"
              size="md"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={trimmed.length === 0 || saving}
            >
              <Icon name="plus" size={14} />
              {submitLabel}
            </Button>
          </footer>
        </form>
      </div>
    </div>
  );
}
