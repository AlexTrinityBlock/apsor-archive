import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  getListFrequentlyUsedPromptsQueryKey,
  useCreateFrequentlyUsedPrompt,
  useDeleteFrequentlyUsedPrompt,
  useListFrequentlyUsedPrompts,
  useUpdateFrequentlyUsedPrompt,
} from "../../generated-apis-types";
import type {
  FrequentlyUsedPromptCreateSchema,
  FrequentlyUsedPromptReadSchema,
  FrequentlyUsedPromptUpdateSchema,
  ListResponseSchemaFrequentlyUsedPromptReadSchema,
} from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { apiErrorMessage } from "./settings-utils";
import { SettingsDialog } from "./SettingsDialog";

type PromptList = ListResponseSchemaFrequentlyUsedPromptReadSchema;

interface PromptEditorState {
  readonly prompt: FrequentlyUsedPromptReadSchema | null;
  readonly defaultSortOrder: number;
}

function sortPrompts(
  prompts: readonly FrequentlyUsedPromptReadSchema[],
): FrequentlyUsedPromptReadSchema[] {
  return [...prompts].sort(
    (left, right) => left.sort_order - right.sort_order || left.id - right.id,
  );
}

function nextSortOrder(
  prompts: readonly FrequentlyUsedPromptReadSchema[],
): number {
  const highest = prompts.reduce(
    (current, prompt) => Math.max(current, prompt.sort_order),
    0,
  );
  return highest + 10;
}

function PromptEditorDialog({
  prompt,
  defaultSortOrder,
  saving,
  error,
  onClose,
  onSubmit,
}: {
  readonly prompt: FrequentlyUsedPromptReadSchema | null;
  readonly defaultSortOrder: number;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (
    data: FrequentlyUsedPromptCreateSchema | FrequentlyUsedPromptUpdateSchema,
  ) => void;
}) {
  const { t, formatNumber } = useI18n();
  const formId = useId();
  const fieldId = useId();
  const [title, setTitle] = useState(prompt?.title ?? "");
  const [promptText, setPromptText] = useState(prompt?.prompt_text ?? "");
  const [sortOrder, setSortOrder] = useState(
    String(prompt?.sort_order ?? defaultSortOrder),
  );
  const [formError, setFormError] = useState<string | null>(null);

  const titleId = `${fieldId}-title`;
  const textId = `${fieldId}-text`;
  const orderId = `${fieldId}-order`;
  let submitLabel = prompt
    ? t("settings.prompts.submitSave")
    : t("settings.prompts.submitAdd");
  if (saving) {
    submitLabel = t("settings.prompts.saving");
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (trimmedTitle.length === 0) {
      setFormError(t("settings.prompts.errors.titleRequired"));
      return;
    }
    if (trimmedTitle.length > 80) {
      setFormError(t("settings.prompts.errors.titleMax"));
      return;
    }
    const trimmedText = promptText.trim();
    if (trimmedText.length === 0) {
      setFormError(t("settings.prompts.errors.textRequired"));
      return;
    }
    if (trimmedText.length > 4000) {
      setFormError(t("settings.prompts.errors.textMax"));
      return;
    }
    const parsedOrder = Number(sortOrder.trim().length === 0 ? "0" : sortOrder);
    if (!Number.isInteger(parsedOrder) || parsedOrder < 0) {
      setFormError(t("settings.prompts.errors.sortOrder"));
      return;
    }
    setFormError(null);
    onSubmit({
      title: trimmedTitle,
      prompt_text: trimmedText,
      sort_order: parsedOrder,
    });
  };

  return (
    <SettingsDialog
      eyebrow={t("settings.prompts.dialogEyebrow")}
      title={
        prompt
          ? t("settings.prompts.editTitle")
          : t("settings.prompts.addTitle")
      }
      description={t("settings.prompts.dialogDescription")}
      onClose={onClose}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={saving}
          >
            {t("settings.common.cancel")}
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="ink"
            size="sm"
            disabled={saving}
          >
            {submitLabel}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="prompt-form"
        onSubmit={handleSubmit}
        aria-busy={saving}
        noValidate
      >
        <label className="field" htmlFor={titleId}>
          <span className="field-label">{t("settings.prompts.fieldTitle")}</span>
          <input
            id={titleId}
            className="input"
            type="text"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              setFormError(null);
            }}
            maxLength={80}
            placeholder={t("settings.prompts.titlePlaceholder")}
            disabled={saving}
            data-autofocus
          />
          <span className="field-help">{t("settings.prompts.titleHelp")}</span>
        </label>

        <label className="field" htmlFor={orderId}>
          <span className="field-label">
            {t("settings.prompts.fieldSortOrder")}
          </span>
          <input
            id={orderId}
            className="input prompt-form__order"
            type="number"
            min={0}
            step={1}
            value={sortOrder}
            onChange={(event) => {
              setSortOrder(event.target.value);
              setFormError(null);
            }}
            disabled={saving}
          />
          <span className="field-help">{t("settings.prompts.sortHelp")}</span>
        </label>

        <label className="field" htmlFor={textId}>
          <span className="field-label">
            {t("settings.prompts.fieldPromptText")}
          </span>
          <textarea
            id={textId}
            className="textarea prompt-form__text"
            value={promptText}
            onChange={(event) => {
              setPromptText(event.target.value);
              setFormError(null);
            }}
            maxLength={4000}
            rows={7}
            placeholder={t("settings.prompts.promptPlaceholder")}
            disabled={saving}
          />
          <span className="field-help prompt-form__count">
            {t("settings.prompts.charCount", {
              count: formatNumber(promptText.length),
            })}
          </span>
        </label>

        {formError ?? error ? (
          <p className="vault-feedback vault-feedback--error" role="alert">
            <Icon name="info" size={14} />
            {formError ?? error}
          </p>
        ) : null}
      </form>
    </SettingsDialog>
  );
}

/** Editable prompt shortcuts shown on the empty chat page. */
export function FrequentlyUsedPromptsPanel() {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const query = useListFrequentlyUsedPrompts({
    query: { staleTime: 30_000 },
  });
  const [editor, setEditor] = useState<PromptEditorState | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] =
    useState<FrequentlyUsedPromptReadSchema | null>(null);

  const prompts = query.data?.resources ?? [];

  const invalidateList = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: getListFrequentlyUsedPromptsQueryKey(),
    });
  };

  const createMutation = useCreateFrequentlyUsedPrompt({
    mutation: {
      onMutate: () => setMutationError(null),
      onSuccess: async (created) => {
        queryClient.setQueryData<PromptList>(
          getListFrequentlyUsedPromptsQueryKey(),
          (current) => {
            if (!current) {
              return current;
            }
            const resources = sortPrompts([...current.resources, created]);
            return {
              ...current,
              resources,
              total_results: resources.length,
            };
          },
        );
        await invalidateList();
        setEditor(null);
        toast.success(t("settings.prompts.addedToast"));
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  const updateMutation = useUpdateFrequentlyUsedPrompt({
    mutation: {
      onMutate: () => setMutationError(null),
      onSuccess: async (updated) => {
        queryClient.setQueryData<PromptList>(
          getListFrequentlyUsedPromptsQueryKey(),
          (current) => {
            if (!current) {
              return current;
            }
            const resources = sortPrompts(
              current.resources.map((prompt) =>
                prompt.id === updated.id ? updated : prompt,
              ),
            );
            return { ...current, resources, total_results: resources.length };
          },
        );
        await invalidateList();
        setEditor(null);
        toast.success(t("settings.prompts.updatedToast"));
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  const deleteMutation = useDeleteFrequentlyUsedPrompt({
    mutation: {
      onMutate: () => setMutationError(null),
      onSuccess: async (_data, variables) => {
        queryClient.setQueryData<PromptList>(
          getListFrequentlyUsedPromptsQueryKey(),
          (current) => {
            if (!current) {
              return current;
            }
            const resources = current.resources.filter(
              (prompt) => prompt.id !== variables.promptId,
            );
            return { ...current, resources, total_results: resources.length };
          },
        );
        await invalidateList();
        setDeleteTarget(null);
        toast.success(t("settings.prompts.deletedToast"));
      },
      onError: (error) => {
        toast.error(apiErrorMessage(error));
      },
    },
  });

  const saving = createMutation.isPending || updateMutation.isPending;
  const limitReached = prompts.length >= 20;

  const openCreate = () => {
    setMutationError(null);
    setEditor({
      prompt: null,
      defaultSortOrder: nextSortOrder(prompts),
    });
  };

  const openEdit = (prompt: FrequentlyUsedPromptReadSchema) => {
    setMutationError(null);
    setEditor({ prompt, defaultSortOrder: prompt.sort_order });
  };

  let body: ReactNode;
  if (query.isPending) {
    body = (
      <div className="prompt-list" role="status" aria-busy="true">
        <span className="settings-skeleton settings-skeleton--line" />
        <span className="settings-skeleton settings-skeleton--line is-short" />
        <span className="settings-skeleton settings-skeleton--field" />
      </div>
    );
  } else if (query.isError) {
    body = (
      <div className="settings-inline-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>{t("settings.prompts.loadErrorTitle")}</strong>
          <p>{apiErrorMessage(query.error)}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <Icon name="ring" size={14} />
            {query.isFetching
              ? t("core.common.retrying")
              : t("core.common.retry")}
          </Button>
        </div>
      </div>
    );
  } else if (prompts.length === 0) {
    body = (
      <div className="prompt-empty">
        <p className="prompt-empty__title">
          {t("settings.prompts.emptyTitle")}
        </p>
        <p className="prompt-empty__copy">
          {t("settings.prompts.emptyCopy")}
        </p>
        <Button type="button" variant="ink" size="sm" onClick={openCreate}>
          <Icon name="plus" size={13} />
          {t("settings.prompts.addFirst")}
        </Button>
      </div>
    );
  } else {
    body = (
      <div className="prompt-list">
        {prompts.map((prompt) => (
          <article className="prompt-row" key={prompt.id}>
            <div className="prompt-row__main">
              <div className="prompt-row__title">
                <h3>{prompt.title}</h3>
                <span className="prompt-row__order">
                  {t("settings.prompts.order", {
                    order: formatNumber(prompt.sort_order),
                  })}
                </span>
              </div>
              <p className="prompt-row__preview" title={prompt.prompt_text}>
                {prompt.prompt_text}
              </p>
            </div>
            <div className="prompt-row__actions">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => openEdit(prompt)}
                disabled={saving || deleteMutation.isPending}
              >
                <Icon name="pencil" size={13} />
                {t("settings.prompts.edit")}
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => setDeleteTarget(prompt)}
                disabled={saving || deleteMutation.isPending}
              >
                <Icon name="trash" size={13} />
                {t("settings.prompts.delete")}
              </Button>
            </div>
          </article>
        ))}
      </div>
    );
  }

  return (
    <>
      <Panel
        id="settings-frequent-prompts"
        title={
          <span className="settings-panel__title">
            <Icon name="quote" size={16} />
            {t("settings.prompts.title")}
          </span>
        }
        action={
          <div className="settings-panel__badges">
            <Badge tone="neutral">
              {formatNumber(prompts.length)} / 20
            </Badge>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={openCreate}
              disabled={query.isPending || query.isError || limitReached}
            >
              <Icon name="plus" size={13} />
              {t("settings.prompts.add")}
            </Button>
          </div>
        }
        className="settings-panel prompt-panel"
      >
        <p className="settings-lede">{t("settings.prompts.lede")}</p>

        {body}

        <p className="settings-hint">{t("settings.prompts.hint")}</p>
      </Panel>

      {editor ? (
        <PromptEditorDialog
          key={editor.prompt?.id ?? "new"}
          prompt={editor.prompt}
          defaultSortOrder={editor.defaultSortOrder}
          saving={saving}
          error={mutationError}
          onClose={() => {
            if (!saving) {
              setEditor(null);
              setMutationError(null);
            }
          }}
          onSubmit={(data) => {
            if (editor.prompt) {
              updateMutation.mutate({
                promptId: editor.prompt.id,
                data,
              });
              return;
            }
            createMutation.mutate({ data });
          }}
        />
      ) : null}

      {deleteTarget ? (
        <SettingsDialog
          eyebrow={t("settings.prompts.dialogEyebrow")}
          title={t("settings.prompts.deleteDialogTitle")}
          description={t("settings.prompts.deleteDialogDescription", {
            title: deleteTarget.title,
          })}
          onClose={() => {
            if (!deleteMutation.isPending) {
              setDeleteTarget(null);
            }
          }}
          actions={
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setDeleteTarget(null)}
                disabled={deleteMutation.isPending}
                data-autofocus
              >
                {t("settings.common.cancel")}
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() =>
                  deleteMutation.mutate({ promptId: deleteTarget.id })
                }
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending
                  ? t("settings.prompts.deleting")
                  : t("settings.prompts.deletePrompt")}
              </Button>
            </>
          }
        >
          <p className="settings-lede">
            {t("settings.prompts.deleteDialogCopy")}
          </p>
        </SettingsDialog>
      ) : null}
    </>
  );
}
