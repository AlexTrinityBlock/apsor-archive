import {
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { ApiError } from "../../apis/fetch-client";
import { formatDateTime, formatNumber, formatRelative } from "../../lib/format";
import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useToast } from "../component/Toast";
import { CitationChip } from "../chat/component/CitationChip";
import { parseCitationLabel, type CitationToken } from "../chat/types";
import {
  getGetAgentConversationQueryKey,
  getListAgentConversationsQueryKey,
  getListAgentEntriesQueryKey,
  getListSavedQuestionsQueryKey,
  useAskSavedQuestion,
  useCreateSavedQuestion,
  useDeleteSavedQuestion,
  useListSavedQuestions,
  useUpdateSavedQuestion,
} from "../generated-apis-types";
import type {
  SavedQuestionListSchema,
  SavedQuestionReadSchema,
} from "../generated-apis-types/schemas";
import type { BadgeTone } from "../type/ui";
import "../chat/chat.css";
import "./questions.css";

const PAGE_SIZE = 50;
const QUESTION_MAX_CHARS = 32_000;

interface StatusMeta {
  readonly label: string;
  readonly tone: BadgeTone;
  readonly dot: boolean;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.detail.trim();
    if (detail.length > 0) {
      return detail;
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "The archive could not complete that request.";
}

function statusMeta(status: SavedQuestionReadSchema["run_status"]): StatusMeta {
  switch (status) {
    case "running":
      return { label: "Running", tone: "ochre", dot: true };
    case "waiting":
      return { label: "Waiting", tone: "ochre", dot: true };
    case "completed":
      return { label: "Answered", tone: "moss", dot: true };
    case "failed":
      return { label: "Failed", tone: "vermilion", dot: true };
    case "cancelled":
      return { label: "Cancelled", tone: "neutral", dot: true };
    default:
      return { label: "Not asked", tone: "neutral", dot: false };
  }
}

function questionNoun(total: number): string {
  return total === 1 ? "question" : "questions";
}

function savedCountLabel(total: number, loaded: boolean): string {
  if (!loaded) {
    return "Reading the book";
  }
  return `${formatNumber(total)} saved ${questionNoun(total)}`;
}

function bookBadgeLabel(total: number, loaded: boolean): string {
  return loaded ? `${formatNumber(total)} in the book` : "Reading";
}

function savedCitationToken(label: string): CitationToken | null {
  const trimmed = label.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const bracketed = trimmed.startsWith("[") ? trimmed : `[${trimmed}]`;
  return parseCitationLabel(bracketed);
}

function answerPlaceholder(item: SavedQuestionReadSchema): string {
  if (item.run_status === "failed") {
    return "The run failed before an answer was recorded.";
  }
  if (item.run_status === "cancelled") {
    return "The run was cancelled before an answer was recorded.";
  }
  if (item.run_status === "running" || item.run_status === "waiting") {
    return "The agent is still working on this question.";
  }
  return "Not asked yet.";
}

function replaceQuestion(
  list: SavedQuestionListSchema | undefined,
  question: SavedQuestionReadSchema,
): SavedQuestionListSchema | undefined {
  if (!list) {
    return list;
  }
  return {
    ...list,
    resources: list.resources.map((item) =>
      item.id === question.id ? question : item,
    ),
  };
}

function QuestionSkeleton() {
  return (
    <article className="question-card question-card--skeleton" aria-hidden="true">
      <span className="question-skeleton question-skeleton--folio" />
      <span className="question-skeleton question-skeleton--title" />
      <span className="question-skeleton question-skeleton--title is-short" />
      <span className="question-skeleton question-skeleton--answer" />
      <span className="question-skeleton question-skeleton--meta" />
    </article>
  );
}

function runErrorTitle(status: SavedQuestionReadSchema["run_status"]): string {
  return status === "cancelled" ? "Run cancelled" : "Run failed";
}

function runErrorFallback(item: SavedQuestionReadSchema): string {
  if (item.run_status === "cancelled") {
    return "The run was cancelled before the agent returned an answer.";
  }
  return "The agent did not return a readable error detail.";
}

async function invalidateAfterAsk(
  queryClient: QueryClient,
  conversationId: number | null,
): Promise<void> {
  const invalidations = [
    queryClient.invalidateQueries({
      queryKey: getListSavedQuestionsQueryKey(),
    }),
    queryClient.invalidateQueries({
      queryKey: getListAgentConversationsQueryKey(),
    }),
  ];
  if (conversationId !== null) {
    invalidations.push(
      queryClient.invalidateQueries({
        queryKey: getGetAgentConversationQueryKey(conversationId),
      }),
      queryClient.invalidateQueries({
        queryKey: getListAgentEntriesQueryKey(conversationId),
      }),
    );
  }
  await Promise.all(invalidations);
}

interface QuestionEditFormProps {
  readonly fieldId: string;
  readonly text: string;
  readonly error: string | null;
  readonly saving: boolean;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly onCancel: () => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}

function QuestionEditForm({
  fieldId,
  text,
  error,
  saving,
  onChange,
  onSubmit,
  onCancel,
  onKeyDown,
}: QuestionEditFormProps) {
  return (
    <form className="question-card__edit" onSubmit={onSubmit}>
      <label className="eyebrow" htmlFor={fieldId}>
        Edit question
      </label>
      <textarea
        id={fieldId}
        value={text}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        rows={3}
        maxLength={QUESTION_MAX_CHARS}
        disabled={saving}
        autoFocus
        aria-describedby={`${fieldId}-hint`}
      />
      <div className="question-card__edit-foot">
        <p className="question-card__edit-hint" id={`${fieldId}-hint`}>
          Saving changed text clears the stored answer and conversation link.
        </p>
        <div className="question-card__edit-actions">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={text.trim().length === 0 || saving}
          >
            <Icon name="check" size={14} />
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onCancel}
            disabled={saving}
          >
            Cancel
          </Button>
        </div>
      </div>
      {error ? (
        <p className="question-card__error" role="alert">
          <Icon name="info" size={14} />
          <span>{error}</span>
        </p>
      ) : null}
    </form>
  );
}

interface QuestionBodyProps {
  readonly item: SavedQuestionReadSchema;
  readonly asking: boolean;
  readonly askingError: string | null;
}

function QuestionBody({ item, asking, askingError }: QuestionBodyProps) {
  const citationTokens = item.citations.map((label) => ({
    label,
    token: savedCitationToken(label),
  }));
  const hasRunError =
    item.run_status === "failed" ||
    item.run_status === "cancelled" ||
    item.error_detail !== null ||
    item.error_code !== null;

  return (
    <>
      <h2 className="question-card__question">{item.question}</h2>

      <div className="question-card__answer">
        <p className="eyebrow">Answer</p>
        {item.answer !== null && item.answer.trim().length > 0 ? (
          <p className="question-card__answer-text">{item.answer}</p>
        ) : (
          <p className="question-card__quiet">{answerPlaceholder(item)}</p>
        )}
      </div>

      {citationTokens.length > 0 ? (
        <div className="question-card__citations">
          <p className="eyebrow">Citations</p>
          <div className="question-card__chips">
            {citationTokens.map(({ label, token }, index) =>
              token ? (
                <CitationChip
                  key={`${token.kind}:${token.id}:${token.chunk ?? "none"}:${index}`}
                  token={token}
                />
              ) : (
                <span
                  className="question-card__raw-citation"
                  key={`${label}:${index}`}
                >
                  {label}
                </span>
              ),
            )}
          </div>
        </div>
      ) : null}

      {hasRunError ? (
        <div className="question-card__run-error" role="status">
          <Icon name="info" size={15} />
          <div>
            <strong>
              {runErrorTitle(item.run_status)}
              {item.error_code ? (
                <code className="question-card__error-code">
                  {item.error_code}
                </code>
              ) : null}
            </strong>
            <p>{item.error_detail ?? runErrorFallback(item)}</p>
          </div>
        </div>
      ) : null}

      {asking ? (
        <p className="question-card__pending" role="status">
          <Loader size={16} label="Asking the archive" />
          Asking the archive. This can take several seconds.
        </p>
      ) : null}

      {askingError ? (
        <p className="question-card__error" role="alert">
          <Icon name="info" size={14} />
          <span>{askingError}</span>
        </p>
      ) : null}
    </>
  );
}

interface QuestionFooterProps {
  readonly item: SavedQuestionReadSchema;
  readonly busy: boolean;
  readonly asking: boolean;
  readonly confirmingDelete: boolean;
  readonly deleting: boolean;
  readonly onAsk: () => void;
  readonly onEdit: () => void;
  readonly onDeleteRequest: () => void;
  readonly onConfirmDelete: () => void;
  readonly onKeep: () => void;
}

function QuestionFooter({
  item,
  busy,
  asking,
  confirmingDelete,
  deleting,
  onAsk,
  onEdit,
  onDeleteRequest,
  onConfirmDelete,
  onKeep,
}: QuestionFooterProps) {
  return (
    <footer className="question-card__foot">
      <div className="question-card__meta">
        <span>
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
        <span>
          Updated{" "}
          <time dateTime={item.updated_at} title={formatDateTime(item.updated_at)}>
            {formatRelative(item.updated_at)}
          </time>
        </span>
        {item.conversation_id !== null ? (
          <Link
            className="question-card__conversation"
            to={`/chat/${item.conversation_id}`}
          >
            <Icon name="chat" size={12} />
            Open conversation
          </Link>
        ) : null}
      </div>

      <div className="question-card__actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={onAsk}
          disabled={busy}
        >
          <Icon name="spark" size={14} />
          {asking ? "Asking…" : "Ask agent"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onEdit}
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
            <span className="question-delete-confirm__label">
              Delete question?
            </span>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={onConfirmDelete}
              disabled={deleting}
            >
              {deleting ? "Deleting…" : "Delete"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onKeep}
              disabled={deleting}
            >
              Keep
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDeleteRequest}
            disabled={busy}
          >
            <Icon name="trash" size={13} />
            Delete
          </Button>
        )}
      </div>
    </footer>
  );
}

interface QuestionCardProps {
  readonly item: SavedQuestionReadSchema;
  readonly listOffset: number;
  readonly onDeleted: (questionId: number) => void;
}

function QuestionCard({ item, listOffset, onDeleted }: QuestionCardProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const editFieldId = useId();

  const [askingError, setAskingError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(item.question);
  const [editOriginal, setEditOriginal] = useState(item.question);
  const [editError, setEditError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const listQueryKey = getListSavedQuestionsQueryKey({
    limit: PAGE_SIZE,
    offset: listOffset,
  });

  const cacheQuestion = (updated: SavedQuestionReadSchema) => {
    queryClient.setQueryData<SavedQuestionListSchema>(listQueryKey, (current) =>
      replaceQuestion(current, updated),
    );
  };

  const askQuestion = useAskSavedQuestion({
    mutation: {
      onMutate: () => {
        setAskingError(null);
      },
      onSuccess: async (updated) => {
        cacheQuestion(updated);
        if (updated.run_status === "failed") {
          toast.error(
            "The agent run failed. The question and its error detail were kept.",
          );
        } else if (updated.run_status === "cancelled") {
          toast.info("The agent run was cancelled. The card was kept.");
        } else {
          toast.success("Answer saved to the question book.");
        }

        await invalidateAfterAsk(queryClient, updated.conversation_id);
      },
      onError: (error) => {
        const detail = errorMessage(error);
        setAskingError(detail);
        toast.error(detail);
      },
    },
  });

  const updateQuestion = useUpdateSavedQuestion({
    mutation: {
      onSuccess: async (updated, variables) => {
        const changed = variables.data.question !== editOriginal;
        const hadAnswer = item.answer !== null || item.conversation_id !== null;
        setEditing(false);
        setEditError(null);
        setEditText(updated.question);
        setEditOriginal(updated.question);
        cacheQuestion(updated);
        toast.success(
          changed && hadAnswer
            ? "Question updated. The previous answer was cleared."
            : "Question updated.",
        );
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
      },
      onError: (error) => {
        setEditError(errorMessage(error));
      },
    },
  });

  const deleteQuestion = useDeleteSavedQuestion({
    mutation: {
      onSuccess: async () => {
        setConfirmingDelete(false);
        toast.success("Question removed from the book.");
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
        onDeleted(item.id);
      },
      onError: (error) => {
        const detail = errorMessage(error);
        setConfirmingDelete(false);
        setAskingError(detail);
        toast.error(detail);
      },
    },
  });

  const asking = askQuestion.isPending;
  const saving = updateQuestion.isPending;
  const deleting = deleteQuestion.isPending;
  const busy = asking || saving || deleting;
  const status = statusMeta(item.run_status);

  const startEditing = () => {
    setAskingError(null);
    setEditText(item.question);
    setEditOriginal(item.question);
    setEditError(null);
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
    setEditError(null);
    setEditText(item.question);
    setEditOriginal(item.question);
  };

  const saveEdit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = editText.trim();
    if (trimmed.length === 0 || saving) {
      return;
    }
    setEditError(null);
    updateQuestion.mutate({
      questionId: item.id,
      data: { question: trimmed },
    });
  };

  const handleEditKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
    if (event.key === "Escape" && !saving) {
      event.preventDefault();
      cancelEditing();
    }
  };

  return (
    <article
      className={[
        "question-card",
        asking ? "is-asking" : null,
        item.run_status === "failed" ? "is-failed" : null,
      ]
        .filter(Boolean)
        .join(" ")}
      aria-busy={asking}
    >
      <header className="question-card__top">
        <span className="question-card__folio">
          Q-{String(item.id).padStart(3, "0")}
        </span>
        <div className="question-card__status">
          <Badge tone={status.tone} dot={status.dot}>
            {status.label}
          </Badge>
        </div>
      </header>

      {editing ? (
        <QuestionEditForm
          fieldId={editFieldId}
          text={editText}
          error={editError}
          saving={saving}
          onChange={(value) => {
            setEditText(value);
            setEditError(null);
          }}
          onSubmit={saveEdit}
          onCancel={cancelEditing}
          onKeyDown={handleEditKeyDown}
        />
      ) : (
        <QuestionBody
          item={item}
          asking={asking}
          askingError={askingError}
        />
      )}

      {!editing ? (
        <QuestionFooter
          item={item}
          busy={busy}
          asking={asking}
          confirmingDelete={confirmingDelete}
          deleting={deleting}
          onAsk={() => askQuestion.mutate({ questionId: item.id })}
          onEdit={startEditing}
          onDeleteRequest={() => {
            setAskingError(null);
            setConfirmingDelete(true);
          }}
          onConfirmDelete={() => deleteQuestion.mutate({ questionId: item.id })}
          onKeep={() => setConfirmingDelete(false)}
        />
      ) : null}
    </article>
  );
}

/** The saved-question book: capture a question, ask it later, and keep the answer. */
export function QuestionsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const questionFieldId = useId();
  const questionHintId = `${questionFieldId}-hint`;
  const questionInputRef = useRef<HTMLTextAreaElement>(null);

  const [offset, setOffset] = useState(0);
  const [draft, setDraft] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const listQuery = useListSavedQuestions(
    { limit: PAGE_SIZE, offset },
    { query: { staleTime: 15_000 } },
  );
  const list = listQuery.data;
  const total = list?.total ?? 0;
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = list && list.resources.length > 0 ? offset + 1 : 0;
  const rangeEnd = list ? Math.min(offset + list.resources.length, total) : 0;

  const createQuestion = useCreateSavedQuestion({
    mutation: {
      onSuccess: async () => {
        setDraft("");
        setFormError(null);
        setOffset(0);
        toast.success("Question saved to the book.");
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
        questionInputRef.current?.focus();
      },
      onError: (error) => {
        setFormError(errorMessage(error));
      },
    },
  });

  const submitQuestion = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = draft.trim();
    if (question.length === 0 || createQuestion.isPending) {
      return;
    }
    setFormError(null);
    createQuestion.mutate({ data: { question } });
  };

  const handleComposeKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const handleDeleted = (questionId: number) => {
    queryClient.setQueryData<SavedQuestionListSchema>(
      getListSavedQuestionsQueryKey({ limit: PAGE_SIZE, offset }),
      (current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          total: Math.max(0, current.total - 1),
          resources: current.resources.filter((item) => item.id !== questionId),
        };
      },
    );
    if (list && list.resources.length === 1 && offset > 0) {
      setOffset((current) => Math.max(0, current - PAGE_SIZE));
    }
  };

  let listBody;
  if (listQuery.isPending) {
    listBody = (
      <div
        className="questions-cards"
        aria-busy="true"
        aria-label="Reading saved questions"
        role="status"
      >
        <QuestionSkeleton />
        <QuestionSkeleton />
        <QuestionSkeleton />
      </div>
    );
  } else if (listQuery.isError && !list) {
    listBody = (
      <Panel tone="plain" className="questions-query-error">
        <p className="eyebrow">Reading interrupted</p>
        <h2>The question book did not answer.</h2>
        <p>{errorMessage(listQuery.error)}</p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => void listQuery.refetch()}
          disabled={listQuery.isFetching}
        >
          <Icon name="ring" size={14} />
          {listQuery.isFetching ? "Retrying…" : "Retry"}
        </Button>
      </Panel>
    );
  } else if (!list || total === 0) {
    listBody = (
      <Panel tone="moss" className="questions-empty">
        <div className="questions-empty__mark" aria-hidden="true">
          <Icon name="quote" size={26} />
        </div>
        <p className="eyebrow">Blank pages</p>
        <h2>No saved questions yet.</h2>
        <p>
          Write a question above and keep it here until you are ready to ask the
          archive. Answers, citations, and their conversation stay beside it.
        </p>
      </Panel>
    );
  } else if (list.resources.length === 0) {
    listBody = (
      <Panel tone="plain" className="questions-query-error">
        <p className="eyebrow">Past the last page</p>
        <h2>This page of the book is empty.</h2>
        <p>
          The question book changed while this page was open. Return to the
          newest entries to continue reading.
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setOffset(0)}
        >
          <Icon name="arrow-right" size={14} className="is-flipped" />
          Back to the first page
        </Button>
      </Panel>
    );
  } else {
    listBody = (
      <>
        <div className="questions-cards">
          {list.resources.map((item) => (
            <QuestionCard
              key={item.id}
              item={item}
              listOffset={offset}
              onDeleted={handleDeleted}
            />
          ))}
        </div>

        {total > PAGE_SIZE ? (
          <nav
            className="questions-pagination"
            aria-label="Saved question pages"
          >
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() =>
                setOffset((current) => Math.max(0, current - PAGE_SIZE))
              }
              disabled={offset === 0 || listQuery.isFetching}
            >
              <Icon name="chevron-right" size={14} className="is-flipped" />
              Previous
            </Button>
            <span className="questions-pagination__label">
              Page {formatNumber(pageNumber)} of {formatNumber(totalPages)} ·{" "}
              {formatNumber(rangeStart)}–{formatNumber(rangeEnd)} of{" "}
              {formatNumber(total)}
            </span>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setOffset((current) => current + PAGE_SIZE)}
              disabled={
                offset + PAGE_SIZE >= total || listQuery.isFetching
              }
            >
              Next
              <Icon name="chevron-right" size={14} />
            </Button>
          </nav>
        ) : null}
      </>
    );
  }

  return (
    <div className="page questions-page">
      <PageHeader
        eyebrow="Question book"
        title="Saved questions"
        description="Keep a question before you have an answer. Ask the archive when you are ready; the answer, its citations, and the conversation return to this page."
        meta={<span>{savedCountLabel(total, list !== undefined)}</span>}
        actions={
          <Badge tone="ochre" dot>
            {bookBadgeLabel(total, list !== undefined)}
          </Badge>
        }
      />

      <Panel
        eyebrow="New entry"
        title="Add a question to the book."
        className="questions-compose reveal reveal-2"
      >
        <form className="questions-form" onSubmit={submitQuestion}>
          <div className="questions-form__head">
            <label className="eyebrow" htmlFor={questionFieldId}>
              Question
            </label>
            <span className="questions-form__hint" id={questionHintId}>
              <kbd>⌘</kbd>/<kbd>Ctrl</kbd> + <kbd>Enter</kbd> to save
            </span>
          </div>
          <textarea
            ref={questionInputRef}
            id={questionFieldId}
            name="question"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              setFormError(null);
            }}
            onKeyDown={handleComposeKeyDown}
            placeholder="What should the archive answer later?"
            rows={3}
            maxLength={QUESTION_MAX_CHARS}
            autoComplete="off"
            disabled={createQuestion.isPending}
            aria-describedby={questionHintId}
            aria-busy={createQuestion.isPending}
          />
          <div className="questions-form__foot">
            <span className="questions-form__note">
              Plain text. Saving is separate from asking; no conversation is
              created until you press Ask agent.
            </span>
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={
                draft.trim().length === 0 || createQuestion.isPending
              }
            >
              <Icon name="plus" size={15} />
              {createQuestion.isPending ? "Adding…" : "Add question"}
            </Button>
          </div>
          {formError ? (
            <p className="questions-inline-error" role="alert">
              <Icon name="info" size={15} />
              <span>{formError}</span>
            </p>
          ) : null}
        </form>
      </Panel>

      <section className="questions-list reveal reveal-3" aria-labelledby="questions-list-title">
        <div className="questions-list__head">
          <div>
            <p className="eyebrow">The book</p>
            <h2 id="questions-list-title">Saved questions</h2>
          </div>
          <span className="questions-list__count">
            {list
              ? `${formatNumber(rangeStart)}–${formatNumber(rangeEnd)} of ${formatNumber(total)}`
              : "Reading"}
          </span>
        </div>

        {listQuery.isError && list ? (
          <div className="questions-inline-error" role="alert">
            <Icon name="info" size={15} />
            <span>
              The book could not refresh. {errorMessage(listQuery.error)}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void listQuery.refetch()}
              disabled={listQuery.isFetching}
            >
              {listQuery.isFetching ? "Retrying…" : "Retry"}
            </Button>
          </div>
        ) : null}

        {listBody}
      </section>
    </div>
  );
}
