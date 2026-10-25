import { useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { ApiError } from "../../apis/fetch-client";
import {
  useApiErrorMessage,
  useI18n,
  type Translate,
  type TranslationKey,
} from "../i18n";
import { Button } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useToast } from "../component/Toast";
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
import { QuestionCard, QuestionCardSkeleton } from "./component/QuestionCard";
import { QuestionDialog } from "./component/QuestionDialog";
import "./questions.css";

const PAGE_SIZE = 50;

type StatusFilter = "all" | "answered" | "running" | "failed";

const STATUS_TABS: readonly {
  readonly value: StatusFilter;
  readonly labelKey: TranslationKey;
  readonly dot: "answered" | "running" | "failed" | null;
}[] = [
  { value: "all", labelKey: "memory.questions.statusAll", dot: null },
  {
    value: "answered",
    labelKey: "memory.questions.statusAnswered",
    dot: "answered",
  },
  {
    value: "running",
    labelKey: "memory.questions.statusRunning",
    dot: "running",
  },
  {
    value: "failed",
    labelKey: "memory.questions.statusFailed",
    dot: "failed",
  },
];

type DialogState =
  | { readonly mode: "create" }
  | { readonly mode: "edit"; readonly item: SavedQuestionReadSchema };

interface CardActionError {
  readonly id: number;
  readonly message: string;
}

function isAiUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 503 || error.code === "ai_not_configured")
  );
}

function isRunActive(status: SavedQuestionReadSchema["run_status"]): boolean {
  return status === "running" || status === "waiting";
}

function statusBucket(
  status: SavedQuestionReadSchema["run_status"],
): StatusFilter | "other" {
  switch (status) {
    case "completed":
      return "answered";
    case "running":
    case "waiting":
      return "running";
    case "failed":
      return "failed";
    default:
      return "other";
  }
}

function matchesText(item: SavedQuestionReadSchema, query: string): boolean {
  if (query.length === 0) {
    return true;
  }
  return [
    item.question,
    item.answer ?? "",
    item.citations.join(" "),
  ]
    .join(" ")
    .toLowerCase()
    .includes(query);
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

function buildToolbarNote(
  list: SavedQuestionListSchema | undefined,
  pageNumber: number,
  totalPages: number,
  loaded: number,
  total: number,
  filteredCount: number,
  filtersActive: boolean,
  t: Translate,
  formatNumber: (value: number) => string,
): string {
  if (!list) {
    return t("memory.questions.toolbarNoPage");
  }
  const base = t("memory.questions.toolbarPage", {
    page: formatNumber(pageNumber),
    totalPages: formatNumber(totalPages),
    loaded: formatNumber(loaded),
    total: formatNumber(total),
  });
  if (!filtersActive) {
    return base;
  }
  const suffix = t(
    filteredCount === 1
      ? "memory.questions.toolbarMatchOne"
      : "memory.questions.toolbarMatchOther",
    { count: formatNumber(filteredCount) },
  );
  return `${base}${suffix}`;
}

interface QuestionShelfBodyProps {
  readonly list: SavedQuestionListSchema | undefined;
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly isFetching: boolean;
  readonly error: unknown;
  readonly total: number;
  readonly resources: readonly SavedQuestionReadSchema[];
  readonly filtered: readonly SavedQuestionReadSchema[];
  readonly offset: number;
  readonly pageNumber: number;
  readonly totalPages: number;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly askingId: number | null;
  readonly deletingId: number | null;
  readonly actionError: CardActionError | null;
  readonly onRetry: () => void;
  readonly onBackToFirstPage: () => void;
  readonly onClearFilters: () => void;
  readonly onCreate: () => void;
  readonly onAsk: (item: SavedQuestionReadSchema) => void;
  readonly onEdit: (item: SavedQuestionReadSchema) => void;
  readonly onDelete: (item: SavedQuestionReadSchema) => void;
  readonly onOffsetChange: (offset: number) => void;
}

/** Loading, error, empty, filtered, and populated states for the shelf. */
function QuestionShelfBody({
  list,
  isPending,
  isError,
  isFetching,
  error,
  total,
  resources,
  filtered,
  offset,
  pageNumber,
  totalPages,
  rangeStart,
  rangeEnd,
  askingId,
  deletingId,
  actionError,
  onRetry,
  onBackToFirstPage,
  onClearFilters,
  onCreate,
  onAsk,
  onEdit,
  onDelete,
  onOffsetChange,
}: QuestionShelfBodyProps) {
  const { t, formatNumber } = useI18n();
  const apiErrorMessage = useApiErrorMessage();

  if (isPending) {
    return (
      <div
        className="question-list"
        aria-busy="true"
        aria-label={t("memory.questions.loadingAria")}
        role="status"
      >
        <QuestionCardSkeleton />
        <QuestionCardSkeleton />
        <QuestionCardSkeleton />
      </div>
    );
  }

  if (isError && !list) {
    return (
      <Panel tone="plain" className="question-error">
        <div className="question-error__body">
          <p className="eyebrow">{t("memory.questions.loadErrorEyebrow")}</p>
          <h2>{t("memory.questions.loadErrorTitle")}</h2>
          <p>
            {apiErrorMessage(error, "memory.questions.toast.couldNotComplete")}
          </p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onRetry}
            disabled={isFetching}
          >
            <Icon name="ring" size={14} />
            {isFetching
              ? t("memory.questions.retrying")
              : t("memory.questions.retry")}
          </Button>
        </div>
      </Panel>
    );
  }

  if (total === 0) {
    return (
      <EmptyState
        icon="quote"
        eyebrow={t("memory.questions.emptyEyebrow")}
        title={t("memory.questions.emptyTitle")}
        description={t("memory.questions.emptyDescription")}
        action={
          <Button type="button" variant="primary" size="md" onClick={onCreate}>
            <Icon name="plus" size={14} />
            {t("memory.questions.saveQuestion")}
          </Button>
        }
      />
    );
  }

  if (resources.length === 0) {
    return (
      <Panel tone="plain" className="question-error">
        <div className="question-error__body">
          <p className="eyebrow">{t("memory.questions.pastPageEyebrow")}</p>
          <h2>{t("memory.questions.pastPageTitle")}</h2>
          <p>{t("memory.questions.pastPageDescription")}</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onBackToFirstPage}
          >
            <Icon name="arrow-right" size={14} className="is-flipped" />
            {t("memory.questions.backToFirstPage")}
          </Button>
        </div>
      </Panel>
    );
  }

  if (filtered.length === 0) {
    return (
      <EmptyState
        icon="filter"
        eyebrow={t("memory.questions.filteredEyebrow")}
        title={t("memory.questions.filteredTitle")}
        description={t("memory.questions.filteredDescription")}
        action={
          <Button type="button" variant="secondary" size="sm" onClick={onClearFilters}>
            {t("memory.questions.clearFilters")}
          </Button>
        }
      />
    );
  }

  return (
    <>
      <div className="question-list" aria-busy={isFetching}>
        {filtered.map((item) => (
          <QuestionCard
            key={item.id}
            item={item}
            asking={askingId === item.id}
            deleting={deletingId === item.id}
            actionError={actionError?.id === item.id ? actionError.message : null}
            onAsk={onAsk}
            onEdit={onEdit}
            onDelete={onDelete}
          />
        ))}
      </div>

      {total > PAGE_SIZE ? (
        <nav
          className="pagination question-pagination"
          aria-label={t("memory.questions.paginationAria")}
        >
          <button
            type="button"
            className="pagination__btn"
            onClick={() => onOffsetChange(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0 || isFetching}
          >
            {t("memory.questions.previous")}
          </button>
          <span className="question-pagination__label">
            {t("memory.questions.pageOf", {
              page: formatNumber(pageNumber),
              totalPages: formatNumber(totalPages),
              start: formatNumber(rangeStart),
              end: formatNumber(rangeEnd),
              total: formatNumber(total),
            })}
          </span>
          <button
            type="button"
            className="pagination__btn"
            onClick={() => onOffsetChange(offset + PAGE_SIZE)}
            disabled={offset + PAGE_SIZE >= total || isFetching}
          >
            {t("memory.questions.next")}
          </button>
        </nav>
      ) : null}
    </>
  );
}

/**
 * The saved-question shelf.
 *
 * The list endpoint has no status or text parameters, so the toolbar filters
 * the loaded page only and every count is labelled as such. Asking a question
 * runs one synchronous agent turn and then opens its conversation in Chat.
 */
export function QuestionsPage() {
  const { t, formatNumber } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const filterId = useId();

  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [textFilter, setTextFilter] = useState("");
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<CardActionError | null>(null);
  const [askingId, setAskingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const listQuery = useListSavedQuestions(
    { limit: PAGE_SIZE, offset },
    {
      query: {
        staleTime: 15_000,
        refetchInterval: (query) =>
          query.state.data?.resources.some((item) =>
            isRunActive(item.run_status),
          )
            ? 10_000
            : false,
      },
    },
  );

  const list = listQuery.data;
  const resources = useMemo(() => list?.resources ?? [], [list]);
  const total = list?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const rangeStart = resources.length > 0 ? offset + 1 : 0;
  const rangeEnd = list ? Math.min(offset + resources.length, total) : 0;

  const listQueryKey = getListSavedQuestionsQueryKey({
    limit: PAGE_SIZE,
    offset,
  });

  const counts = useMemo(() => {
    const next = { all: resources.length, answered: 0, running: 0, failed: 0 };
    for (const item of resources) {
      const bucket = statusBucket(item.run_status);
      if (bucket === "answered" || bucket === "running" || bucket === "failed") {
        next[bucket] += 1;
      }
    }
    return next;
  }, [resources]);

  const query = textFilter.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      resources.filter(
        (item) =>
          (statusFilter === "all" || statusBucket(item.run_status) === statusFilter) &&
          matchesText(item, query),
      ),
    [resources, statusFilter, query],
  );

  const filtersActive = statusFilter !== "all" || query.length > 0;

  const createQuestion = useCreateSavedQuestion({
    mutation: {
      onSuccess: async (created) => {
        setDialog(null);
        setDialogError(null);
        setStatusFilter("all");
        setTextFilter("");
        setOffset(0);
        toast.success(t("memory.questions.toast.saved"));
        queryClient.setQueryData<SavedQuestionListSchema>(
          getListSavedQuestionsQueryKey({ limit: PAGE_SIZE, offset: 0 }),
          (current) =>
            current
              ? {
                  ...current,
                  total: current.total + 1,
                  resources: [created, ...current.resources].slice(0, PAGE_SIZE),
                }
              : current,
        );
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
      },
      onError: (error) => {
        setDialogError(
          apiErrorMessage(error, "memory.questions.toast.couldNotComplete"),
        );
      },
    },
  });

  const updateQuestion = useUpdateSavedQuestion({
    mutation: {
      onSuccess: async (updated, variables) => {
        const editing = dialog?.mode === "edit" ? dialog.item : null;
        const changed = editing !== null && variables.data.question !== editing.question;
        const hadAnswer =
          editing !== null &&
          (editing.answer !== null || editing.conversation_id !== null);
        setDialog(null);
        setDialogError(null);
        toast.success(
          changed && hadAnswer
            ? t("memory.questions.toast.updatedAnswerCleared")
            : t("memory.questions.toast.updated"),
        );
        queryClient.setQueryData<SavedQuestionListSchema>(listQueryKey, (current) =>
          replaceQuestion(current, updated),
        );
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
      },
      onError: (error) => {
        setDialogError(
          apiErrorMessage(error, "memory.questions.toast.couldNotComplete"),
        );
      },
    },
  });

  const askQuestion = useAskSavedQuestion({
    mutation: {
      onMutate: (variables) => {
        setAskingId(variables.questionId);
        setActionError(null);
      },
      onSuccess: async (updated) => {
        setAiNotice(null);
        queryClient.setQueryData<SavedQuestionListSchema>(listQueryKey, (current) =>
          replaceQuestion(current, updated),
        );
        if (updated.run_status === "failed") {
          toast.error(t("memory.questions.toast.askFailed"));
        } else if (updated.run_status === "cancelled") {
          toast.info(t("memory.questions.toast.askCancelled"));
        } else {
          toast.success(t("memory.questions.toast.answerSaved"));
        }
        await invalidateAfterAsk(queryClient, updated.conversation_id);
        if (updated.conversation_id !== null) {
          navigate(`/chat/${updated.conversation_id}`);
        }
      },
      onError: (error, variables) => {
        if (isAiUnavailable(error)) {
          setAiNotice(
            apiErrorMessage(error, "memory.questions.toast.couldNotComplete"),
          );
          toast.error(t("memory.questions.toast.aiNotConfigured"));
        } else {
          const detail = apiErrorMessage(
            error,
            "memory.questions.toast.couldNotComplete",
          );
          setActionError({ id: variables.questionId, message: detail });
          toast.error(detail);
        }
      },
      onSettled: () => {
        setAskingId(null);
      },
    },
  });

  const deleteQuestion = useDeleteSavedQuestion({
    mutation: {
      onMutate: (variables) => {
        setDeletingId(variables.questionId);
        setActionError(null);
      },
      onSuccess: async (_result, variables) => {
        toast.success(t("memory.questions.toast.removed"));
        queryClient.setQueryData<SavedQuestionListSchema>(listQueryKey, (current) =>
          current
            ? {
                ...current,
                total: Math.max(0, current.total - 1),
                resources: current.resources.filter(
                  (item) => item.id !== variables.questionId,
                ),
              }
            : current,
        );
        await queryClient.invalidateQueries({
          queryKey: getListSavedQuestionsQueryKey(),
        });
        if (resources.length === 1 && offset > 0) {
          setOffset(Math.max(0, offset - PAGE_SIZE));
        }
      },
      onError: (error, variables) => {
        const detail = apiErrorMessage(
          error,
          "memory.questions.toast.couldNotComplete",
        );
        setActionError({ id: variables.questionId, message: detail });
        toast.error(detail);
      },
      onSettled: () => {
        setDeletingId(null);
      },
    },
  });

  const dialogSaving =
    dialog?.mode === "edit" ? updateQuestion.isPending : createQuestion.isPending;

  const openCreate = () => {
    setDialogError(null);
    setDialog({ mode: "create" });
  };

  const openEdit = (item: SavedQuestionReadSchema) => {
    setDialogError(null);
    setDialog({ mode: "edit", item });
  };

  const closeDialog = () => {
    setDialog(null);
    setDialogError(null);
  };

  const submitDialog = (question: string) => {
    setDialogError(null);
    if (!dialog) {
      return;
    }
    if (dialog.mode === "create") {
      createQuestion.mutate({ data: { question } });
      return;
    }
    updateQuestion.mutate({ questionId: dialog.item.id, data: { question } });
  };

  const clearFilters = () => {
    setStatusFilter("all");
    setTextFilter("");
  };

  const toolbarNote = buildToolbarNote(
    list,
    pageNumber,
    totalPages,
    resources.length,
    total,
    filtered.length,
    filtersActive,
    t,
    formatNumber,
  );

  return (
    <div className="page questions-page">
      <div className="content-container">
        <PageHeader
          eyebrow={t("memory.questions.eyebrow")}
          title={t("memory.questions.title")}
          description={t("memory.questions.description")}
          meta={
            <span>
              {list
                ? t("memory.questions.metaLoadedSaved", {
                    loaded: formatNumber(resources.length),
                    total: formatNumber(total),
                  })
                : t("memory.questions.metaReading")}
            </span>
          }
        />

        <section
          className="question-toolbar"
          aria-label={t("memory.questions.shelfControlsAria")}
        >
          <div
            className="question-toolbar__tabs"
            role="group"
            aria-label={t("memory.questions.filterAria")}
          >
            {STATUS_TABS.map((tab) => {
              const active = statusFilter === tab.value;
              return (
                <button
                  key={tab.value}
                  type="button"
                  className={`question-tab${active ? " is-active" : ""}`}
                  aria-pressed={active}
                  onClick={() => setStatusFilter(tab.value)}
                >
                  {tab.dot ? (
                    <span
                      className={`question-tab__dot question-tab__dot--${tab.dot}`}
                      aria-hidden="true"
                    />
                  ) : null}
                  <span>{t(tab.labelKey)}</span>
                  <span
                    className="question-tab__count"
                    title={t("memory.questions.countOnPageTitle")}
                  >
                    {formatNumber(counts[tab.value])}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="question-toolbar__tools">
            <div className="question-filter" role="search">
              <Icon name="search" size={15} />
              <label className="visually-hidden" htmlFor={filterId}>
                {t("memory.questions.textFilterLabel")}
              </label>
              <input
                id={filterId}
                type="search"
                value={textFilter}
                onChange={(event) => setTextFilter(event.target.value)}
                placeholder={t("memory.questions.textFilterPlaceholder")}
                autoComplete="off"
                spellCheck={false}
              />
              {textFilter.length > 0 ? (
                <button
                  type="button"
                  className="question-filter__clear"
                  aria-label={t("memory.questions.clearTextFilterAria")}
                  onClick={() => setTextFilter("")}
                >
                  <Icon name="close" size={13} />
                </button>
              ) : null}
            </div>
            <Button type="button" variant="ink" size="md" onClick={openCreate}>
              <Icon name="plus" size={14} />
              {t("memory.questions.saveQuestion")}
            </Button>
          </div>

          <p className="question-toolbar__note">{toolbarNote}</p>
        </section>

        {aiNotice ? (
          <div className="question-notice question-notice--seal" role="status">
            <Icon name="info" size={15} />
            <p>
              <strong>{t("memory.questions.aiNoticeTitle")}</strong>{" "}
              {aiNotice} {t("memory.questions.aiNoticeBody")}
            </p>
            <Link className="question-notice__link" to="/settings">
              {t("memory.questions.openSettings")}
              <Icon name="arrow-right" size={13} />
            </Link>
            <button
              type="button"
              className="question-notice__dismiss"
              aria-label={t("memory.questions.dismissProviderNotice")}
              onClick={() => setAiNotice(null)}
            >
              <Icon name="close" size={14} />
            </button>
          </div>
        ) : null}

        {listQuery.isError && list ? (
          <div className="question-notice" role="alert">
            <Icon name="info" size={15} />
            <p>
              {t("memory.questions.refreshFailed", {
                detail: apiErrorMessage(
                  listQuery.error,
                  "memory.questions.toast.couldNotComplete",
                ),
              })}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void listQuery.refetch()}
              disabled={listQuery.isFetching}
            >
              {listQuery.isFetching
                ? t("memory.questions.retrying")
                : t("memory.questions.retry")}
            </Button>
          </div>
        ) : null}

        <QuestionShelfBody
          list={list}
          isPending={listQuery.isPending}
          isError={listQuery.isError}
          isFetching={listQuery.isFetching}
          error={listQuery.error}
          total={total}
          resources={resources}
          filtered={filtered}
          offset={offset}
          pageNumber={pageNumber}
          totalPages={totalPages}
          rangeStart={rangeStart}
          rangeEnd={rangeEnd}
          askingId={askingId}
          deletingId={deletingId}
          actionError={actionError}
          onRetry={() => void listQuery.refetch()}
          onBackToFirstPage={() => setOffset(0)}
          onClearFilters={clearFilters}
          onCreate={openCreate}
          onAsk={(item) => askQuestion.mutate({ questionId: item.id })}
          onEdit={openEdit}
          onDelete={(item) => deleteQuestion.mutate({ questionId: item.id })}
          onOffsetChange={setOffset}
        />
      </div>

      {dialog ? (
        <QuestionDialog
          key={dialog.mode === "edit" ? `edit-${dialog.item.id}` : "create"}
          mode={dialog.mode}
          initialQuestion={dialog.mode === "edit" ? dialog.item.question : ""}
          saving={dialogSaving}
          error={dialogError}
          onClose={closeDialog}
          onSubmit={submitDialog}
        />
      ) : null}
    </div>
  );
}
