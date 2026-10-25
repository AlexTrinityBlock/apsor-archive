import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

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
  useReorderFrequentlyUsedPrompts,
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

/** A six-dot grip, kept local because the shared icon set has no drag mark. */
function GripIcon() {
  return (
    <svg
      className="prompt-row__grip"
      viewBox="0 0 14 20"
      width="14"
      height="20"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="4" cy="4" r="1.4" />
      <circle cx="10" cy="4" r="1.4" />
      <circle cx="4" cy="10" r="1.4" />
      <circle cx="10" cy="10" r="1.4" />
      <circle cx="4" cy="16" r="1.4" />
      <circle cx="10" cy="16" r="1.4" />
    </svg>
  );
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
  const [formError, setFormError] = useState<string | null>(null);

  const titleId = `${fieldId}-title`;
  const textId = `${fieldId}-text`;
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
    setFormError(null);
    onSubmit({
      title: trimmedTitle,
      prompt_text: trimmedText,
      sort_order: prompt?.sort_order ?? defaultSortOrder,
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

interface SortablePromptRowProps {
  readonly prompt: FrequentlyUsedPromptReadSchema;
  readonly actionsDisabled: boolean;
  readonly dragDisabled: boolean;
  readonly onEdit: () => void;
  readonly onRequestDelete: () => void;
}

/** One prompt row; only the grip starts a drag so the actions stay clickable. */
function SortablePromptRow({
  prompt,
  actionsDisabled,
  dragDisabled,
  onEdit,
  onRequestDelete,
}: SortablePromptRowProps) {
  const { t } = useI18n();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: prompt.id, disabled: dragDisabled });

  const classes = ["prompt-row", isDragging ? "is-dragging" : null]
    .filter(Boolean)
    .join(" ");

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={classes}
    >
      <button
        type="button"
        className="prompt-row__drag"
        {...attributes}
        {...listeners}
        aria-label={t("settings.prompts.reorderAria", {
          title: prompt.title,
        })}
        title={t("settings.prompts.reorderTitle")}
      >
        <GripIcon />
      </button>

      <div className="prompt-row__main">
        <div className="prompt-row__title">
          <h3>{prompt.title}</h3>
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
          onClick={onEdit}
          disabled={actionsDisabled}
        >
          <Icon name="pencil" size={13} />
          {t("settings.prompts.edit")}
        </Button>
        <Button
          type="button"
          variant="danger"
          size="sm"
          onClick={onRequestDelete}
          disabled={actionsDisabled}
        >
          <Icon name="trash" size={13} />
          {t("settings.prompts.delete")}
        </Button>
      </div>
    </li>
  );
}

interface SortablePromptListProps {
  readonly prompts: readonly FrequentlyUsedPromptReadSchema[];
  readonly saving: boolean;
  readonly deleting: boolean;
  readonly onDragActiveChange: (active: boolean) => void;
  readonly onEdit: (prompt: FrequentlyUsedPromptReadSchema) => void;
  readonly onRequestDelete: (prompt: FrequentlyUsedPromptReadSchema) => void;
}

/** The sortable list; every drop persists the complete order immediately. */
function SortablePromptList({
  prompts,
  saving,
  deleting,
  onDragActiveChange,
  onEdit,
  onRequestDelete,
}: SortablePromptListProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const toast = useToast();
  const listKey = getListFrequentlyUsedPromptsQueryKey();
  const [dragging, setDragging] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const reorderMutation = useReorderFrequentlyUsedPrompts({
    mutation: {
      onSuccess: async (data) => {
        queryClient.setQueryData<PromptList>(listKey, data);
        await queryClient.invalidateQueries({
          queryKey: getListFrequentlyUsedPromptsQueryKey(),
        });
      },
      onError: (caught) => {
        void queryClient.invalidateQueries({
          queryKey: getListFrequentlyUsedPromptsQueryKey(),
        });
        toast.error(apiErrorMessage(caught));
      },
    },
  });

  const setDragActive = (active: boolean) => {
    setDragging(active);
    onDragActiveChange(active);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setDragActive(false);
    const { active, over } = event;
    if (!over) {
      return;
    }
    const activeId = Number(active.id);
    const overId = Number(over.id);
    if (Number.isNaN(activeId) || Number.isNaN(overId) || activeId === overId) {
      return;
    }
    const current = queryClient.getQueryData<PromptList>(listKey);
    if (!current) {
      return;
    }
    const oldIndex = current.resources.findIndex(
      (prompt) => prompt.id === activeId,
    );
    const newIndex = current.resources.findIndex(
      (prompt) => prompt.id === overId,
    );
    if (oldIndex < 0 || newIndex < 0) {
      return;
    }
    const moved = arrayMove(current.resources, oldIndex, newIndex).map(
      (prompt, index) => ({
        ...prompt,
        sort_order: (index + 1) * 10,
      }),
    );
    queryClient.setQueryData<PromptList>(listKey, {
      ...current,
      resources: moved,
      total_results: moved.length,
    });
    reorderMutation.mutate({
      data: { prompt_ids: moved.map((prompt) => prompt.id) },
    });
  };

  const actionsDisabled =
    saving || deleting || reorderMutation.isPending || dragging;
  const dragDisabled = saving || deleting || reorderMutation.isPending;

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={() => setDragActive(true)}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setDragActive(false)}
    >
      <SortableContext
        items={prompts.map((prompt) => prompt.id)}
        strategy={verticalListSortingStrategy}
      >
        <ul
          className="prompt-list"
          aria-label={t("settings.prompts.title")}
        >
          {prompts.map((prompt) => (
            <SortablePromptRow
              key={prompt.id}
              prompt={prompt}
              actionsDisabled={actionsDisabled}
              dragDisabled={dragDisabled}
              onEdit={() => onEdit(prompt)}
              onRequestDelete={() => onRequestDelete(prompt)}
            />
          ))}
        </ul>
      </SortableContext>
    </DndContext>
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
  const [dragActive, setDragActive] = useState(false);

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
      <SortablePromptList
        prompts={prompts}
        saving={saving}
        deleting={deleteMutation.isPending}
        onDragActiveChange={setDragActive}
        onEdit={openEdit}
        onRequestDelete={(prompt) => setDeleteTarget(prompt)}
      />
    );
  }

  return (
    <>
      <Panel
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
              disabled={
                query.isPending || query.isError || limitReached || dragActive
              }
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
