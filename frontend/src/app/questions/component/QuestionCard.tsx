import { useState } from "react";
import { Link } from "react-router-dom";

import { formatDateTime, formatRelative } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import type { SavedQuestionReadSchema } from "../../generated-apis-types/schemas";
import type { BadgeTone } from "../../type/ui";
import { QuestionCitations } from "./citations";

interface StatusMeta {
  readonly label: string;
  readonly tone: BadgeTone;
  readonly dot: boolean;
}

const STATUS: Record<string, StatusMeta> = {
  completed: { label: "Answered", tone: "moss", dot: true },
  running: { label: "Running", tone: "ochre", dot: true },
  waiting: { label: "Running", tone: "ochre", dot: true },
  failed: { label: "Failed", tone: "vermilion", dot: true },
  cancelled: { label: "Cancelled", tone: "neutral", dot: false },
};

const NOT_ASKED: StatusMeta = { label: "Not asked", tone: "neutral", dot: false };

function statusMeta(status: SavedQuestionReadSchema["run_status"]): StatusMeta {
  return status === null ? NOT_ASKED : (STATUS[status] ?? NOT_ASKED);
}

function isRunActive(status: SavedQuestionReadSchema["run_status"]): boolean {
  return status === "running" || status === "waiting";
}

function answerPlaceholder(item: SavedQuestionReadSchema): string {
  if (item.run_status === "failed") {
    return "The run failed before an answer was recorded.";
  }
  if (item.run_status === "cancelled") {
    return "The run was cancelled before an answer was recorded.";
  }
  if (isRunActive(item.run_status)) {
    return "The agent is still working on this question.";
  }
  return "Not asked yet. Run this question in Chat to record an answer.";
}

function errorTitle(item: SavedQuestionReadSchema): string {
  return item.run_status === "cancelled" ? "Run cancelled" : "Run failed";
}

function errorFallback(item: SavedQuestionReadSchema): string {
  return item.run_status === "cancelled"
    ? "The run was cancelled before the agent returned an answer."
    : "The agent did not return a readable error detail.";
}

function runButtonLabel(asking: boolean, runActive: boolean, retry: boolean): string {
  if (asking) {
    return "Asking…";
  }
  if (runActive) {
    return "Running…";
  }
  return retry ? "Retry" : "Run in Chat";
}

interface QuestionCardProps {
  readonly item: SavedQuestionReadSchema;
  readonly asking: boolean;
  readonly deleting: boolean;
  readonly actionError: string | null;
  readonly onAsk: (item: SavedQuestionReadSchema) => void;
  readonly onEdit: (item: SavedQuestionReadSchema) => void;
  readonly onDelete: (item: SavedQuestionReadSchema) => void;
}

/** One saved question with its answer, receipts, and shelf actions. */
export function QuestionCard({
  item,
  asking,
  deleting,
  actionError,
  onAsk,
  onEdit,
  onDelete,
}: QuestionCardProps) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const status = statusMeta(item.run_status);
  const runActive = isRunActive(item.run_status);
  const retry = item.run_status === "failed" || item.run_status === "cancelled";
  const cancelled = item.run_status === "cancelled";
  const hasRunError = item.run_status === "failed" || cancelled;
  const busy = asking || deleting;

  const classes = [
    "question-card",
    asking ? "is-asking" : null,
    runActive ? "is-running" : null,
    item.run_status === "failed" ? "is-failed" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article className={classes} aria-busy={busy}>
      <header className="question-card__head">
        <span className="question-card__folio">
          FOLIO Q-{String(item.id).padStart(3, "0")}
        </span>
        <Badge tone={status.tone} dot={status.dot}>
          {status.label}
        </Badge>
      </header>

      <h2 className="question-card__question">{item.question}</h2>

      {runActive ? (
        <div className="question-banner question-banner--running" role="status">
          <span className="question-banner__pulse" aria-hidden="true" />
          <div>
            <p className="question-banner__title">Run in progress</p>
            <p>
              The agent is still working on this question. The shelf refreshes
              while a run is active.
            </p>
          </div>
        </div>
      ) : null}

      {hasRunError ? (
        <div
          className={`question-banner ${
            cancelled ? "question-banner--cancelled" : "question-banner--failed"
          }`}
          role="status"
        >
          <Icon name="info" size={16} />
          <div>
            <p className="question-banner__title">
              {errorTitle(item)}
              {item.error_code ? (
                <code className="question-banner__code">{item.error_code}</code>
              ) : null}
            </p>
            <p>{item.error_detail ?? errorFallback(item)}</p>
          </div>
        </div>
      ) : null}

      <div className="question-card__answer">
        <p className="mono-label">Answer</p>
        {item.answer !== null && item.answer.trim().length > 0 ? (
          <p className="question-card__answer-text">{item.answer}</p>
        ) : (
          <p className="question-card__quiet">{answerPlaceholder(item)}</p>
        )}
        <QuestionCitations citations={item.citations} />
      </div>

      {asking ? (
        <p className="question-banner question-banner--asking">
          <Loader size={14} label="Asking the archive" />
          Asking the archive. This can take several seconds.
        </p>
      ) : null}

      {actionError ? (
        <p className="question-card__error" role="alert">
          <Icon name="info" size={14} />
          <span>{actionError}</span>
        </p>
      ) : null}

      <footer className="question-card__foot">
        <div className="question-card__meta">
          <span className="question-card__meta-item">
            <Icon name="clock" size={12} />
            {item.last_asked_at ? (
              <>
                Asked{" "}
                <time
                  dateTime={item.last_asked_at}
                  title={formatDateTime(item.last_asked_at)}
                >
                  {formatRelative(item.last_asked_at)}
                </time>
              </>
            ) : (
              <>
                Saved{" "}
                <time
                  dateTime={item.created_at}
                  title={formatDateTime(item.created_at)}
                >
                  {formatRelative(item.created_at)}
                </time>
              </>
            )}
          </span>
          <span className="question-card__meta-item">
            Updated{" "}
            <time
              dateTime={item.updated_at}
              title={formatDateTime(item.updated_at)}
            >
              {formatRelative(item.updated_at)}
            </time>
          </span>
          {item.conversation_id !== null ? (
            <Link
              className="question-card__conversation"
              to={`/chat/${item.conversation_id}`}
            >
              <Icon name="chat" size={12} />
              Conversation #{item.conversation_id}
            </Link>
          ) : null}
        </div>

        <div className="question-card__actions">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onEdit(item)}
            disabled={busy}
          >
            <Icon name="pencil" size={13} />
            Edit
          </Button>

          {confirmingDelete ? (
            <div
              className="question-delete-confirm"
              role="group"
              aria-label="Confirm deleting this question"
            >
              <span className="question-delete-confirm__label">Delete?</span>
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={() => onDelete(item)}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setConfirmingDelete(true)}
              disabled={busy}
            >
              <Icon name="trash" size={13} />
              Delete
            </Button>
          )}

          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={() => onAsk(item)}
            disabled={busy || runActive}
          >
            <Icon name={retry ? "history" : "spark"} size={13} />
            {runButtonLabel(asking, runActive, retry)}
          </Button>
        </div>
      </footer>
    </article>
  );
}

/** Loading placeholder that mirrors the card's folio, title, and answer rows. */
export function QuestionCardSkeleton() {
  return (
    <article
      className="question-card question-card--skeleton"
      aria-hidden="true"
    >
      <div className="question-card__head">
        <span className="question-skeleton question-skeleton--folio" />
        <span className="question-skeleton question-skeleton--badge" />
      </div>
      <span className="question-skeleton question-skeleton--title" />
      <span className="question-skeleton question-skeleton--title is-short" />
      <span className="question-skeleton question-skeleton--answer" />
      <span className="question-skeleton question-skeleton--meta" />
    </article>
  );
}
