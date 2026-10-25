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
  let submitLabel = prompt ? "Save prompt" : "Add prompt";
  if (saving) {
    submitLabel = "Saving…";
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (trimmedTitle.length === 0) {
      setFormError("Title is required.");
      return;
    }
    if (trimmedTitle.length > 80) {
      setFormError("Title must be 80 characters or fewer.");
      return;
    }
    const trimmedText = promptText.trim();
    if (trimmedText.length === 0) {
      setFormError("Prompt text is required.");
      return;
    }
    if (trimmedText.length > 4000) {
      setFormError("Prompt text must be 4,000 characters or fewer.");
      return;
    }
    const parsedOrder = Number(sortOrder.trim().length === 0 ? "0" : sortOrder);
    if (!Number.isInteger(parsedOrder) || parsedOrder < 0) {
      setFormError("Sort order must be a whole number of zero or more.");
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
      eyebrow="Settings · frequent prompts"
      title={prompt ? "Edit frequent prompt" : "Add frequent prompt"}
      description="These shortcuts appear on the empty chat page. Clicking one fills the composer with the full prompt text."
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
            Cancel
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
          <span className="field-label">Title</span>
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
            placeholder="Trace a memory"
            disabled={saving}
            data-autofocus
          />
          <span className="field-help">Up to 80 characters.</span>
        </label>

        <label className="field" htmlFor={orderId}>
          <span className="field-label">Sort order</span>
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
          <span className="field-help">
            Lower numbers appear first. Blank is treated as zero.
          </span>
        </label>

        <label className="field" htmlFor={textId}>
          <span className="field-label">Prompt text</span>
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
            placeholder="Trace the lineage of the most recent memory and explain what changed."
            disabled={saving}
          />
          <span className="field-help prompt-form__count">
            {promptText.length.toLocaleString()} / 4,000 characters
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
        toast.success("Frequent prompt added.");
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
        toast.success("Frequent prompt updated.");
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
        toast.success("Frequent prompt deleted.");
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
          <strong>Frequent prompts did not answer.</strong>
          <p>{apiErrorMessage(query.error)}</p>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <Icon name="ring" size={14} />
            {query.isFetching ? "Retrying…" : "Retry"}
          </Button>
        </div>
      </div>
    );
  } else if (prompts.length === 0) {
    body = (
      <div className="prompt-empty">
        <p className="prompt-empty__title">No frequent prompts yet.</p>
        <p className="prompt-empty__copy">
          Add up to 20 shortcuts. Each one appears on the empty chat page and
          fills the composer when clicked.
        </p>
        <Button type="button" variant="ink" size="sm" onClick={openCreate}>
          <Icon name="plus" size={13} />
          Add the first prompt
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
                  Order {prompt.sort_order}
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
                Edit
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => setDeleteTarget(prompt)}
                disabled={saving || deleteMutation.isPending}
              >
                <Icon name="trash" size={13} />
                Delete
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
            Frequently used prompts
          </span>
        }
        action={
          <div className="settings-panel__badges">
            <Badge tone="neutral">{prompts.length} / 20</Badge>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={openCreate}
              disabled={query.isPending || query.isError || limitReached}
            >
              <Icon name="plus" size={13} />
              Add prompt
            </Button>
          </div>
        }
        className="settings-panel prompt-panel"
      >
        <p className="settings-lede">
          Shortcuts for the empty chat room. The list is stored in PostgreSQL
          and appears in the order below; editing it never changes existing
          conversations.
        </p>

        {body}

        <p className="settings-hint">
          Up to 20 prompts. Title and prompt text are trimmed; blank values are
          rejected. Lower sort orders appear first.
        </p>
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
          eyebrow="Settings · frequent prompts"
          title="Delete this prompt?"
          description={`“${deleteTarget.title}” will disappear from the chat page immediately.`}
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
                Cancel
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
                {deleteMutation.isPending ? "Deleting…" : "Delete prompt"}
              </Button>
            </>
          }
        >
          <p className="settings-lede">
            Existing conversations keep their transcripts. This only removes
            the shortcut from the empty chat page.
          </p>
        </SettingsDialog>
      ) : null}
    </>
  );
}
