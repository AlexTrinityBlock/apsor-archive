import { ApiError } from "../../../apis/fetch-client";
import { Badge } from "../../component/Badge";
import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";

const SUGGESTED_QUESTIONS = [
  "What car did the user switch to, and why?",
  "Summarize the workshop memories.",
  "What changed in the automobile archive?",
  "What did the user learn from the 10mm wrench?",
] as const;

interface SuggestedQuestionsProps {
  readonly onSelect: (question: string) => void;
  readonly disabled: boolean;
}

/** The empty reading room, seeded with questions the demo archive can answer. */
export function SuggestedQuestions({ onSelect, disabled }: SuggestedQuestionsProps) {
  return (
    <section className="ask-intro reveal reveal-3">
      <span className="ask-intro__icon" aria-hidden="true">
        <Icon name="ask" size={26} />
      </span>
      <p className="eyebrow">The reading room is open</p>
      <h2>Start with a question the archive can answer.</h2>
      <p className="ask-intro__description">
        Ask about a file, a decision, or a stretch of memory. The archive
        retrieves a small set of current passages first; the answer may only use
        what those passages contain.
      </p>

      <div className="ask-suggestions">
        <span className="ask-suggestions__label">Suggested questions</span>
        {SUGGESTED_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            className="ask-suggestion"
            onClick={() => onSelect(question)}
            disabled={disabled}
          >
            <span>{question}</span>
            <Icon name="arrow-up-right" size={14} />
          </button>
        ))}
      </div>

      <p className="ask-intro__note">
        Answers arrive as plain text with inline citations. No answer is shown
        without the passages that support it.
      </p>
    </section>
  );
}

/** A calm, non-alarming card for the 503 ai_not_configured response. */
export function AiUnavailableCard() {
  return (
    <section className="ask-config-card" role="status">
      <span className="ask-config-card__mark" aria-hidden="true">
        <Icon name="info" size={22} />
      </span>
      <div>
        <p className="eyebrow">AI not configured</p>
        <h2>DeepSeek is not connected.</h2>
        <p>
          Ask needs a key. Set <code>DENDRO_DEEPSEEK_API_KEY</code> in the API
          environment, or in the local <code>.secrets/deepseek.env</code> file,
          then restart the backend.
        </p>
        <p>
          Summaries can still fall back to extractive selection, but this room
          will stay quiet rather than invent an answer.
        </p>
        <div className="ask-config-card__actions">
          <ButtonLink to="/settings" variant="secondary" size="sm">
            Inspect AI status
            <Icon name="arrow-right" size={14} />
          </ButtonLink>
          <ButtonLink to="/method#answers" variant="ghost" size="sm">
            How answers cite
          </ButtonLink>
        </div>
        <div className="ask-config-card__meta">
          <Badge tone="ochre">503 ai_not_configured</Badge>
          <code>POST /api/v1/ask</code>
        </div>
      </div>
    </section>
  );
}

function askErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "The archive did not answer.";
}

interface AskErrorStateProps {
  readonly error: unknown;
}

/** Configuration failures get a calm card; everything else is reported plainly. */
export function AskErrorState({ error }: AskErrorStateProps) {
  if (error instanceof ApiError && error.code === "ai_not_configured") {
    return <AiUnavailableCard />;
  }

  const code = error instanceof ApiError ? error.code : "unknown_error";
  const status = error instanceof ApiError && error.status > 0 ? error.status : null;

  return (
    <section className="ask-error" role="alert">
      <p className="eyebrow">The reading room went quiet</p>
      <h2>The question could not be answered.</h2>
      <p className="ask-error__detail">{askErrorMessage(error)}</p>
      <div className="ask-error__meta">
        <Badge tone="vermilion">{code}</Badge>
        {status === null ? <span>Network request</span> : <span>HTTP {status}</span>}
      </div>
    </section>
  );
}

/** A small live region while the archive retrieves and composes. */
export function AskPending() {
  return (
    <div className="ask-pending" role="status" aria-live="polite">
      <Loader size={26} label="Asking the archive" />
      <div>
        <p className="eyebrow">Reading the grain</p>
        <p>Hybrid search → citations → answer.</p>
      </div>
    </div>
  );
}
