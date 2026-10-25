import {
  useId,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
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
  getListBuiltinSystemPromptSectionsQueryKey,
  getListSystemPromptSectionsQueryKey,
  useCreateSystemPromptSection,
  useDeleteSystemPromptSection,
  useListBuiltinSystemPromptSections,
  useListSystemPromptSections,
  useReorderSystemPromptSections,
  useResetBuiltinSystemPromptSections,
  useResetSystemPromptSections,
  useUpdateBuiltinSystemPromptSection,
  useUpdateSystemPromptSection,
} from "../../generated-apis-types";
import type {
  ListResponseSchemaSystemPromptBuiltinSectionSchema,
  ListResponseSchemaSystemPromptSectionReadSchema,
  SystemPromptBuiltinSectionSchema,
  SystemPromptSectionReadSchema,
} from "../../generated-apis-types/schemas";
import { apiErrorMessage } from "./settings-utils";
import { SettingsDialog } from "./SettingsDialog";

type SectionList = ListResponseSchemaSystemPromptSectionReadSchema;
type BuiltinList = ListResponseSchemaSystemPromptBuiltinSectionSchema;

type PanelActionError =
  | { readonly scope: "create"; readonly message: string }
  | {
      readonly scope: "update";
      readonly sectionId: number;
      readonly message: string;
    }
  | { readonly scope: "delete"; readonly message: string }
  | { readonly scope: "reset"; readonly message: string };

const COLLAPSE_KEY = "apsor-archive.settings.systemPromptOpen";
const SECTION_OPEN_PREFIX = "apsor-archive.systemPrompt.sectionOpen.";

const BUILT_IN_ORDER = [
  "Identity",
  "Instructions",
  "Examples",
  "Context protocol",
  "Tool catalog",
  "Conversation messages",
] as const;

function initiallyOpen(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) !== "false";
  } catch {
    return true;
  }
}

function sectionOpenKey(id: number): string {
  return `${SECTION_OPEN_PREFIX}${id}`;
}

function readSectionOpen(id: number): boolean {
  try {
    return window.localStorage.getItem(sectionOpenKey(id)) !== "false";
  } catch {
    return true;
  }
}

/** Persist only the boolean; section bodies never reach localStorage. */
function writeSectionOpen(id: number, value: boolean): void {
  try {
    window.localStorage.setItem(sectionOpenKey(id), String(value));
  } catch {
    // Storage can be blocked; the in-memory state still works.
  }
}

const DEFAULT_COLLAPSE_KEY = "apsor-archive.settings.systemDefaultOpen";

function initiallyDefaultOpen(): boolean {
  try {
    return window.localStorage.getItem(DEFAULT_COLLAPSE_KEY) !== "false";
  } catch {
    return true;
  }
}

function writeDefaultOpen(value: boolean): void {
  try {
    window.localStorage.setItem(DEFAULT_COLLAPSE_KEY, String(value));
  } catch {
    // Storage can be blocked; the in-memory state still works.
  }
}

const BUILTIN_OPEN_PREFIX = "apsor-archive.systemPrompt.builtinOpen.";

function builtinOpenKey(key: string): string {
  return `${BUILTIN_OPEN_PREFIX}${key}`;
}

function readBuiltinOpen(key: string): boolean {
  try {
    return window.localStorage.getItem(builtinOpenKey(key)) !== "false";
  } catch {
    return true;
  }
}

function writeBuiltinOpen(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(builtinOpenKey(key), String(value));
  } catch {
    // Storage can be blocked; the in-memory state still works.
  }
}

/** A six-dot grip, kept local because the shared icon set has no drag mark. */
function GripIcon() {
  return (
    <svg
      className="system-prompt-section__grip"
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

interface EditorProps {
  readonly section: SystemPromptSectionReadSchema;
  readonly saving: boolean;
  readonly error: string | null;
  readonly titleRef: RefObject<HTMLInputElement | null>;
  readonly onSave: (title: string, body: string) => void;
  readonly onRequestDelete: () => void;
}

/** One expanded section editor; remounted whenever the server copy changes. */
function SystemPromptSectionEditor({
  section,
  saving,
  error,
  titleRef,
  onSave,
  onRequestDelete,
}: EditorProps) {
  const [title, setTitle] = useState(section.title);
  const [body, setBody] = useState(section.body);
  const titleId = useId();
  const bodyId = useId();

  const dirty = title !== section.title || body !== section.body;
  const valid = title.trim().length > 0 && body.trim().length > 0;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || !dirty || saving) {
      return;
    }
    onSave(title.trim(), body.trim());
  };

  return (
    <form
      className="system-prompt-section__editor"
      onSubmit={handleSubmit}
      aria-busy={saving}
      noValidate
    >
      <div className="field system-prompt-section__field">
        <label className="field-label" htmlFor={titleId}>
          Title
        </label>
        <input
          ref={titleRef}
          id={titleId}
          className="input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={200}
          placeholder="Archive voice"
          disabled={saving}
        />
        <span className="field-help">
          Rendered as the Markdown heading of this section.
        </span>
      </div>

      <div className="field system-prompt-section__field">
        <label className="field-label" htmlFor={bodyId}>
          Body
        </label>
        <textarea
          id={bodyId}
          className="textarea system-prompt-section__textarea"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          maxLength={32_000}
          rows={10}
          placeholder="Add persistent instructions. The system default identity and tool rules still follow all custom sections."
          disabled={saving}
        />
        <span className="field-help system-prompt__count">
          {body.length.toLocaleString()} / 32,000 characters
        </span>
      </div>

      {error ? (
        <p className="vault-feedback vault-feedback--error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}

      <div className="system-prompt-section__editor-actions">
        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={!valid || !dirty || saving}
        >
          <Icon name="check" size={14} />
          {saving ? "Saving…" : "Save section"}
        </Button>
        <Button
          type="button"
          variant="danger"
          size="sm"
          onClick={onRequestDelete}
          disabled={saving}
        >
          <Icon name="trash" size={14} />
          Delete
        </Button>
        <span className="system-prompt__meta">
          Updated {new Date(section.updated_at).toLocaleString()}
        </span>
      </div>
    </form>
  );
}

interface SortableSectionProps {
  readonly section: SystemPromptSectionReadSchema;
  readonly index: number;
  readonly saving: boolean;
  readonly dragDisabled: boolean;
  readonly error: string | null;
  readonly onSave: (title: string, body: string) => void;
  readonly onRequestDelete: () => void;
}

/** One sortable, collapsible section card. */
function SortableSection({
  section,
  index,
  saving,
  dragDisabled,
  error,
  onSave,
  onRequestDelete,
}: SortableSectionProps) {
  const [open, setOpen] = useState(() => readSectionOpen(section.id));
  const titleRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const bodyId = useId();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: section.id, disabled: dragDisabled });

  const classes = [
    "system-prompt-section",
    open ? "is-open" : "is-collapsed",
    isDragging ? "is-dragging" : null,
  ]
    .filter(Boolean)
    .join(" ");

  const setOpenState = (next: boolean) => {
    setOpen(next);
    writeSectionOpen(section.id, next);
  };

  const handleEdit = () => {
    if (!open) {
      setOpenState(true);
    }
    window.requestAnimationFrame(() => titleRef.current?.focus());
  };

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={classes}
      aria-labelledby={titleId}
    >
      <div className="system-prompt-section__head">
        <button
          type="button"
          className="system-prompt-section__handle"
          {...attributes}
          {...listeners}
          aria-label={`Reorder ${section.title}`}
          title="Drag to reorder; press Space then use the arrow keys"
        >
          <GripIcon />
        </button>

        <span className="system-prompt-section__index" aria-hidden="true">
          {String(index + 1).padStart(2, "0")}
        </span>

        <div className="system-prompt-section__heading">
          <h3 className="system-prompt-section__title" id={titleId}>
            {section.title}
          </h3>
          <span className="system-prompt-section__meta">
            {section.body.length.toLocaleString()} characters
          </span>
        </div>

        <div className="system-prompt-section__actions">
          <button
            type="button"
            className="system-prompt__collapse system-prompt-section__toggle"
            aria-expanded={open}
            aria-controls={open ? bodyId : undefined}
            onClick={() => setOpenState(!open)}
            title={open ? "Collapse section" : "Expand section"}
          >
            <Icon name={open ? "chevron-down" : "chevron-right"} size={13} />
            <span>{open ? "Collapse" : "Expand"}</span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleEdit}
            disabled={saving}
          >
            <Icon name="pencil" size={13} />
            Edit
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={onRequestDelete}
            disabled={saving}
          >
            <Icon name="trash" size={13} />
            Delete
          </Button>
        </div>
      </div>

      {open ? (
        <div className="system-prompt-section__body" id={bodyId}>
          <SystemPromptSectionEditor
            key={`${section.id}:${section.updated_at}`}
            section={section}
            saving={saving}
            error={error}
            titleRef={titleRef}
            onSave={onSave}
            onRequestDelete={onRequestDelete}
          />
        </div>
      ) : null}
    </li>
  );
}

interface SortableSectionListProps {
  readonly sections: readonly SystemPromptSectionReadSchema[];
  readonly saving: boolean;
  readonly busy: boolean;
  readonly updateError: {
    readonly scope: "update";
    readonly sectionId: number;
    readonly message: string;
  } | null;
  readonly onSave: (sectionId: number, title: string, body: string) => void;
  readonly onRequestDelete: (section: SystemPromptSectionReadSchema) => void;
}

/** The sortable list; drag order is saved immediately through the reorder hook. */
function SortableSectionList({
  sections,
  saving,
  busy,
  updateError,
  onSave,
  onRequestDelete,
}: SortableSectionListProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const listKey = getListSystemPromptSectionsQueryKey();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const reorderMutation = useReorderSystemPromptSections({
    mutation: {
      onSuccess: async (data) => {
        queryClient.setQueryData<SectionList>(listKey, data);
        await queryClient.invalidateQueries({
          queryKey: getListSystemPromptSectionsQueryKey(),
        });
      },
      onError: (caught) => {
        void queryClient.invalidateQueries({
          queryKey: getListSystemPromptSectionsQueryKey(),
        });
        toast.error(apiErrorMessage(caught));
      },
    },
  });

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) {
      return;
    }
    const activeId = Number(active.id);
    const overId = Number(over.id);
    if (Number.isNaN(activeId) || Number.isNaN(overId) || activeId === overId) {
      return;
    }
    const current = queryClient.getQueryData<SectionList>(listKey);
    if (!current) {
      return;
    }
    const oldIndex = current.resources.findIndex(
      (section) => section.id === activeId,
    );
    const newIndex = current.resources.findIndex(
      (section) => section.id === overId,
    );
    if (oldIndex < 0 || newIndex < 0) {
      return;
    }
    const moved = arrayMove(current.resources, oldIndex, newIndex).map(
      (section, index) => ({
        ...section,
        sort_order: (index + 1) * 10,
      }),
    );
    queryClient.setQueryData<SectionList>(listKey, {
      ...current,
      resources: moved,
      total_results: moved.length,
    });
    reorderMutation.mutate({
      data: { section_ids: moved.map((section) => section.id) },
    });
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext
        items={sections.map((section) => section.id)}
        strategy={verticalListSortingStrategy}
      >
        <ul
          className="system-prompt-sections"
          aria-label="Custom system prompt sections"
        >
          {sections.map((section, index) => (
            <SortableSection
              key={section.id}
              section={section}
              index={index}
              saving={saving}
              dragDisabled={busy || reorderMutation.isPending}
              error={
                updateError?.sectionId === section.id
                  ? updateError.message
                  : null
              }
              onSave={(title, body) => onSave(section.id, title, body)}
              onRequestDelete={() => onRequestDelete(section)}
            />
          ))}
        </ul>
      </SortableContext>
    </DndContext>
  );
}

interface ProviderOrderProps {
  readonly sections: readonly SystemPromptSectionReadSchema[];
}

/** The provider-facing order: custom sections first, then every built-in one. */
function ProviderOrderBlock({ sections }: ProviderOrderProps) {
  const orderItems = [
    ...sections.map((section) => ({
      key: `section-${section.id}`,
      label: section.title,
      custom: true,
    })),
    ...BUILT_IN_ORDER.map((label) => ({
      key: `builtin-${label}`,
      label,
      custom: false,
    })),
  ];

  return (
    <div className="system-prompt__order-block">
      <p className="mono-label">Provider request order</p>
      <ol className="system-prompt__order" aria-label="System prompt load order">
        {orderItems.map((item, index) => {
          const itemClasses = [
            index === 0 ? "is-first" : null,
            item.custom ? "is-custom" : null,
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <li key={item.key} className={itemClasses || undefined}>
              <span className="system-prompt__order-index">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="system-prompt__order-label">{item.label}</span>
              {item.custom ? (
                <span className="system-prompt__order-tag">custom</span>
              ) : null}
            </li>
          );
        })}
      </ol>
      <p className="settings-hint">
        Stable order: one system message → tools → append-only messages. The
        current time is appended to each user message when it is sent, so
        history is never rewritten.
      </p>
    </div>
  );
}

interface AddDialogProps {
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onSubmit: (title: string, body: string) => void;
}

/** Collect a new section; the server appends it after the current last one. */
function AddSectionDialog({
  saving,
  error,
  onClose,
  onSubmit,
}: AddDialogProps) {
  const formId = useId();
  const fieldId = useId();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const titleId = `${fieldId}-title`;
  const bodyId = `${fieldId}-body`;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (trimmedTitle.length === 0) {
      setFormError("Title is required.");
      return;
    }
    const trimmedBody = body.trim();
    if (trimmedBody.length === 0) {
      setFormError("Body is required.");
      return;
    }
    setFormError(null);
    onSubmit(trimmedTitle, trimmedBody);
  };

  return (
    <SettingsDialog
      eyebrow="Settings · system prompt"
      title="Add a system prompt section"
      description="New sections are appended after the current last section. Drag them into place once saved."
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
            {saving ? "Adding…" : "Add section"}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="system-prompt-form"
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
            maxLength={200}
            placeholder="Archive voice"
            disabled={saving}
            data-autofocus
          />
          <span className="field-help">Up to 200 characters.</span>
        </label>

        <label className="field" htmlFor={bodyId}>
          <span className="field-label">Body</span>
          <textarea
            id={bodyId}
            className="textarea system-prompt-form__body"
            value={body}
            onChange={(event) => {
              setBody(event.target.value);
              setFormError(null);
            }}
            maxLength={32_000}
            rows={8}
            placeholder="Add persistent instructions for the archive agent."
            disabled={saving}
          />
          <span className="field-help system-prompt__count">
            {body.length.toLocaleString()} / 32,000 characters
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

interface DeleteDialogProps {
  readonly target: SystemPromptSectionReadSchema;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
}

/** Confirm removal of one section. */
function DeleteSectionDialog({
  target,
  saving,
  error,
  onClose,
  onConfirm,
}: DeleteDialogProps) {
  return (
    <SettingsDialog
      eyebrow="Settings · system prompt"
      title="Delete this section?"
      description={`“${target.title}” will be removed from the ordered prompt. Existing conversations keep the prompt frozen at creation.`}
      onClose={onClose}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={saving}
            data-autofocus
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={onConfirm}
            disabled={saving}
          >
            {saving ? "Deleting…" : "Delete section"}
          </Button>
        </>
      }
    >
      <p className="settings-lede">
        The remaining custom sections and the system default still form the
        prompt for new conversations.
      </p>
      {error ? (
        <p className="vault-feedback vault-feedback--error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}
    </SettingsDialog>
  );
}

interface ResetDialogProps {
  readonly count: number;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
}

/** Confirm removal of every custom section. */
function ResetSectionsDialog({
  count,
  saving,
  error,
  onClose,
  onConfirm,
}: ResetDialogProps) {
  const sectionNoun = count === 1 ? "section" : "sections";
  let confirmLabel = `Remove all ${count} ${sectionNoun}`;
  if (saving) {
    confirmLabel = "Removing…";
  }

  return (
    <SettingsDialog
      eyebrow="Settings · system prompt"
      title="Remove every custom section?"
      description="New conversations will use the system default identity, instructions, examples, and context protocol only. Existing conversations keep their frozen prompt."
      onClose={onClose}
      actions={
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={saving}
            data-autofocus
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={onConfirm}
            disabled={saving}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="settings-lede">
        All custom sections are deleted at once. This cannot be undone.
      </p>
      {error ? (
        <p className="vault-feedback vault-feedback--error" role="alert">
          <Icon name="info" size={14} />
          {error}
        </p>
      ) : null}
    </SettingsDialog>
  );
}

interface DialogsProps {
  readonly addOpen: boolean;
  readonly resetOpen: boolean;
  readonly deleteTarget: SystemPromptSectionReadSchema | null;
  readonly actionError: PanelActionError | null;
  readonly sectionCount: number;
  readonly createSaving: boolean;
  readonly deleteSaving: boolean;
  readonly resetSaving: boolean;
  readonly onCloseAdd: () => void;
  readonly onCloseDelete: () => void;
  readonly onCloseReset: () => void;
  readonly onCreate: (title: string, body: string) => void;
  readonly onConfirmDelete: () => void;
  readonly onConfirmReset: () => void;
}

/** All modal states for the panel, grouped so the panel stays readable. */
function SystemPromptDialogs({
  addOpen,
  resetOpen,
  deleteTarget,
  actionError,
  sectionCount,
  createSaving,
  deleteSaving,
  resetSaving,
  onCloseAdd,
  onCloseDelete,
  onCloseReset,
  onCreate,
  onConfirmDelete,
  onConfirmReset,
}: DialogsProps) {
  return (
    <>
      {addOpen ? (
        <AddSectionDialog
          saving={createSaving}
          error={actionError?.scope === "create" ? actionError.message : null}
          onClose={onCloseAdd}
          onSubmit={onCreate}
        />
      ) : null}

      {deleteTarget ? (
        <DeleteSectionDialog
          target={deleteTarget}
          saving={deleteSaving}
          error={actionError?.scope === "delete" ? actionError.message : null}
          onClose={onCloseDelete}
          onConfirm={onConfirmDelete}
        />
      ) : null}

      {resetOpen ? (
        <ResetSectionsDialog
          count={sectionCount}
          saving={resetSaving}
          error={actionError?.scope === "reset" ? actionError.message : null}
          onClose={onCloseReset}
          onConfirm={onConfirmReset}
        />
      ) : null}
    </>
  );
}

interface MutationOptions {
  readonly setActionError: (error: PanelActionError | null) => void;
  readonly onCreated: () => void;
  readonly onDeleted: () => void;
  readonly onReset: () => void;
}

/** Write mutations for the collection; each stores the returned list. */
function useSystemPromptMutations({
  setActionError,
  onCreated,
  onDeleted,
  onReset,
}: MutationOptions) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const listKey = getListSystemPromptSectionsQueryKey();

  const invalidateList = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: getListSystemPromptSectionsQueryKey(),
    });
  };

  const createMutation = useCreateSystemPromptSection({
    mutation: {
      onMutate: () => setActionError(null),
      onSuccess: async (data) => {
        queryClient.setQueryData<SectionList>(listKey, data);
        await invalidateList();
        onCreated();
        toast.success("System prompt section added.");
      },
      onError: (caught) => {
        setActionError({
          scope: "create",
          message: apiErrorMessage(caught),
        });
      },
    },
  });

  const updateMutation = useUpdateSystemPromptSection({
    mutation: {
      onMutate: () => setActionError(null),
      onSuccess: async (data) => {
        queryClient.setQueryData<SectionList>(listKey, data);
        await invalidateList();
        toast.success("System prompt section saved.");
      },
      onError: (caught, variables) => {
        setActionError({
          scope: "update",
          sectionId: variables.sectionId,
          message: apiErrorMessage(caught),
        });
      },
    },
  });

  const deleteMutation = useDeleteSystemPromptSection({
    mutation: {
      onMutate: () => setActionError(null),
      onSuccess: async (_data, variables) => {
        queryClient.setQueryData<SectionList>(listKey, (current) => {
          if (!current) {
            return current;
          }
          const resources = current.resources.filter(
            (section) => section.id !== variables.sectionId,
          );
          return { ...current, resources, total_results: resources.length };
        });
        await invalidateList();
        onDeleted();
        toast.success("System prompt section deleted.");
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught);
        setActionError({ scope: "delete", message });
        toast.error(message);
      },
    },
  });

  const resetMutation = useResetSystemPromptSections({
    mutation: {
      onMutate: () => setActionError(null),
      onSuccess: async (data) => {
        queryClient.setQueryData<SectionList>(listKey, data);
        await invalidateList();
        onReset();
        toast.success("Custom sections removed. System default remains.");
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught);
        setActionError({ scope: "reset", message });
        toast.error(message);
      },
    },
  });

  return { createMutation, updateMutation, deleteMutation, resetMutation };
}

function BuiltinPromptCard({
  section,
  saving,
  disabled,
  error,
  onSave,
}: {
  readonly section: SystemPromptBuiltinSectionSchema;
  readonly saving: boolean;
  readonly disabled: boolean;
  readonly error: string | null;
  readonly onSave: (key: string, body: string) => void;
}) {
  const [open, setOpen] = useState(() => readBuiltinOpen(section.key));
  const [body, setBody] = useState(section.body);
  const titleId = useId();
  const bodyId = useId();

  const dirty = body.trim() !== section.body.trim();
  const setOpenState = (next: boolean) => {
    setOpen(next);
    writeBuiltinOpen(section.key, next);
  };

  return (
    <article
      className={[
        "builtin-prompt-card",
        open ? "is-open" : "is-collapsed",
        section.customized ? "is-customized" : null,
      ]
        .filter(Boolean)
        .join(" ")}
      aria-labelledby={titleId}
    >
      <header className="builtin-prompt-card__head">
        <div className="builtin-prompt-card__title">
          <p className="eyebrow">Default</p>
          <h4 id={titleId}>{section.title}</h4>
        </div>
        {section.customized ? (
          <Badge tone="ochre">Customized</Badge>
        ) : (
          <Badge tone="neutral">Default</Badge>
        )}
        <button
          type="button"
          className="builtin-prompt-card__toggle"
          aria-expanded={open}
          aria-controls={`${bodyId}-panel`}
          onClick={() => setOpenState(!open)}
        >
          {open ? "Collapse" : "Expand"}
          <Icon name={open ? "chevron-down" : "chevron-right"} size={13} />
        </button>
      </header>

      {open ? (
        <div className="builtin-prompt-card__body" id={`${bodyId}-panel`}>
          <label className="field" htmlFor={bodyId}>
            <span className="field-label">Body</span>
            <textarea
              id={bodyId}
              className="textarea builtin-prompt-card__textarea"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              maxLength={32_000}
              rows={10}
              disabled={saving || disabled}
            />
            <span className="field-help">
              {body.length.toLocaleString()} / 32,000 characters
            </span>
          </label>
          <div className="builtin-prompt-card__foot">
            <span className="field-help">
              Applies to conversations created after saving.
            </span>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={() => onSave(section.key, body.trim())}
              disabled={
                saving ||
                disabled ||
                !dirty ||
                body.trim().length === 0
              }
            >
              <Icon name="check" size={13} />
              {saving ? "Saving…" : "Save section"}
            </Button>
          </div>
          {error ? (
            <p className="builtin-prompt-card__error" role="alert">
              <Icon name="info" size={14} />
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

/** Edit the four provider-facing default sections without changing their order. */
export function SystemDefaultPanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const query = useListBuiltinSystemPromptSections({
    query: { retry: false, staleTime: 15_000 },
  });
  const [open, setOpen] = useState(initiallyDefaultOpen);
  const [error, setError] = useState<{
    readonly key: string;
    readonly message: string;
  } | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const listKey = getListBuiltinSystemPromptSectionsQueryKey();

  const updateMutation = useUpdateBuiltinSystemPromptSection({
    mutation: {
      onSuccess: (data) => {
        queryClient.setQueryData<BuiltinList>(listKey, data);
        setError(null);
        toast.success("System default section saved.");
      },
      onError: (caught, variables) => {
        const message = apiErrorMessage(caught);
        setError({ key: variables.key, message });
        toast.error(message);
      },
    },
  });

  const resetMutation = useResetBuiltinSystemPromptSections({
    mutation: {
      onSuccess: (data) => {
        queryClient.setQueryData<BuiltinList>(listKey, data);
        setError(null);
        setResetOpen(false);
        toast.success("System default restored.");
      },
      onError: (caught) => {
        const message = apiErrorMessage(caught);
        toast.error(message);
      },
    },
  });

  const sections = query.data?.resources ?? [];
  const customized = sections.filter((section) => section.customized).length;
  const togglePanel = () => {
    const next = !open;
    setOpen(next);
    writeDefaultOpen(next);
  };

  let badge = (
    <Badge tone={customized > 0 ? "ochre" : "moss"}>
      {customized > 0 ? `${customized} customized` : "Pristine"}
    </Badge>
  );
  if (query.isPending) {
    badge = <Badge tone="neutral">Loading</Badge>;
  } else if (query.isError) {
    badge = <Badge tone="vermilion">Unavailable</Badge>;
  }

  let listBody = null;
  if (query.isPending) {
    listBody = (
      <div className="builtin-prompt__list" aria-busy="true">
        <span className="settings-skeleton settings-skeleton--line" />
        <span className="settings-skeleton settings-skeleton--field" />
        <span className="settings-skeleton settings-skeleton--field" />
      </div>
    );
  } else if (query.isError) {
    listBody = (
      <div className="settings-inline-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>The system default did not answer.</strong>
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
  } else {
    listBody = (
      <div className="builtin-prompt__list">
        {sections.map((section) => (
          <BuiltinPromptCard
            key={`${section.key}:${section.updated_at ?? "default"}`}
            section={section}
            saving={
              updateMutation.isPending &&
              updateMutation.variables?.key === section.key
            }
            disabled={resetMutation.isPending}
            error={error?.key === section.key ? error.message : null}
            onSave={(key, body) =>
              updateMutation.mutate({ key, data: { body } })
            }
          />
        ))}
      </div>
    );
  }

  return (
    <>
      <Panel
        id="settings-system-default"
        className="settings-panel system-default-panel"
        title={
          <span className="settings-panel__title">
            <Icon name="layers" size={16} />
            System default
          </span>
        }
        action={
          <div className="settings-panel__badges">
            {badge}
            <button
              type="button"
              className="system-prompt__collapse"
              aria-expanded={open}
              aria-controls="system-default-body"
              onClick={togglePanel}
              title={open ? "Collapse system default" : "Expand system default"}
            >
              <Icon name={open ? "chevron-down" : "chevron-right"} size={14} />
              <span>{open ? "Collapse" : "Expand"}</span>
            </button>
          </div>
        }
      >
        {open ? (
          <div id="system-default-body" className="builtin-prompt">
            <p className="builtin-prompt__lede">
              These four sections are the provider-facing system default. They
              render after custom sections; editing one stores an override, and
              reset removes every override and restores the server wording. The
              tool catalog and conversation messages remain built by the server.
            </p>
            {listBody}
            <div className="builtin-prompt__foot">
              <span className="field-help">
                Changes apply only to conversations created after saving.
              </span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setError(null);
                  setResetOpen(true);
                }}
                disabled={
                  query.isPending ||
                  query.isError ||
                  customized === 0 ||
                  resetMutation.isPending
                }
              >
                <Icon name="history" size={13} />
                Reset defaults
              </Button>
            </div>
          </div>
        ) : null}
      </Panel>

      {resetOpen ? (
        <SettingsDialog
          eyebrow="Settings · system default"
          title="Reset the system default?"
          description="Every override is removed. Custom sections are untouched, and existing conversations keep their frozen prompt."
          onClose={() => {
            if (!resetMutation.isPending) {
              setResetOpen(false);
            }
          }}
          actions={
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setResetOpen(false)}
                disabled={resetMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
              >
                <Icon name="history" size={14} />
                {resetMutation.isPending ? "Resetting…" : "Reset defaults"}
              </Button>
            </>
          }
        >
          <p className="settings-dialog__copy">
            {customized === 1
              ? "One system default section will return to its default text."
              : `${customized} system default sections will return to their default text.`}
          </p>
        </SettingsDialog>
      ) : null}
    </>
  );
}

/** Ordered custom system prompt sections, frozen per conversation. */
export function CustomSystemPromptPanel() {
  const query = useListSystemPromptSections({
    query: { retry: false, staleTime: 15_000 },
  });
  const [open, setOpen] = useState(initiallyOpen);
  const [addOpen, setAddOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] =
    useState<SystemPromptSectionReadSchema | null>(null);
  const [actionError, setActionError] = useState<PanelActionError | null>(
    null,
  );

  const { createMutation, updateMutation, deleteMutation, resetMutation } =
    useSystemPromptMutations({
      setActionError,
      onCreated: () => setAddOpen(false),
      onDeleted: () => setDeleteTarget(null),
      onReset: () => setResetOpen(false),
    });

  const sections = query.data?.resources ?? [];
  const sectionNoun = sections.length === 1 ? "section" : "sections";
  const saving = updateMutation.isPending;
  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    resetMutation.isPending;

  const togglePanel = () => {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem(COLLAPSE_KEY, String(next));
    } catch {
      // Storage can be blocked; the in-memory state still works.
    }
  };

  const openCreate = () => {
    setActionError(null);
    setAddOpen(true);
  };

  const openDelete = (section: SystemPromptSectionReadSchema) => {
    setActionError(null);
    setDeleteTarget(section);
  };

  let countBadge = (
    <Badge tone="neutral">
      {sections.length} {sectionNoun}
    </Badge>
  );
  if (query.isPending) {
    countBadge = <Badge tone="neutral">Loading</Badge>;
  } else if (query.isError) {
    countBadge = <Badge tone="vermilion">Unavailable</Badge>;
  } else if (sections.length > 0) {
    countBadge = (
      <Badge tone="moss">
        {sections.length} {sectionNoun}
      </Badge>
    );
  }

  let listBody = null;
  if (query.isPending) {
    listBody = (
      <div className="system-prompt-sections" aria-busy="true">
        <span className="settings-skeleton settings-skeleton--line" />
        <span className="settings-skeleton settings-skeleton--field" />
        <span className="settings-skeleton settings-skeleton--field" />
      </div>
    );
  } else if (query.isError) {
    listBody = (
      <div className="settings-inline-error" role="alert">
        <Icon name="info" size={16} />
        <div>
          <strong>Custom system prompt sections did not answer.</strong>
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
  } else if (sections.length === 0) {
    listBody = (
      <div className="system-prompt-empty">
        <p className="system-prompt-empty__copy">
          No custom sections. The system default is used.
        </p>
        <Button type="button" variant="ink" size="sm" onClick={openCreate}>
          <Icon name="plus" size={13} />
          Add the first section
        </Button>
      </div>
    );
  } else {
    listBody = (
      <SortableSectionList
        sections={sections}
        saving={saving}
        busy={busy}
        updateError={
          actionError && actionError.scope === "update" ? actionError : null
        }
        onSave={(sectionId, title, body) =>
          updateMutation.mutate({
            sectionId,
            data: { title, body },
          })
        }
        onRequestDelete={openDelete}
      />
    );
  }

  return (
    <>
      <Panel
        id="settings-system-prompt"
        className="settings-panel system-prompt-panel"
        title={
          <span className="settings-panel__title">
            <Icon name="pencil" size={16} />
            Custom system prompt
          </span>
        }
        action={
          <div className="settings-panel__badges">
            {countBadge}
            <button
              type="button"
              className="system-prompt__collapse"
              aria-expanded={open}
              aria-controls="system-prompt-body"
              onClick={togglePanel}
              title={open ? "Collapse custom system prompt" : "Expand custom system prompt"}
            >
              <Icon name={open ? "chevron-down" : "chevron-right"} size={14} />
              <span>{open ? "Collapse" : "Expand"}</span>
            </button>
          </div>
        }
      >
        {open ? (
          <div id="system-prompt-body" className="system-prompt">
            <p className="settings-lede">
              Custom sections render in this order before the system default.
              Each one becomes a scoped <code>system_prompt:&lt;id&gt;</code> in
              the provider message. Drag a grip to rewrite{" "}
              <code>sort_order</code>; existing conversations keep the prompt
              frozen when they were created.
            </p>

            <ProviderOrderBlock sections={sections} />

            <div className="system-prompt__toolbar">
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={openCreate}
                disabled={query.isPending || query.isError}
              >
                <Icon name="plus" size={13} />
                Add section
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setActionError(null);
                  setResetOpen(true);
                }}
                disabled={
                  query.isPending || query.isError || sections.length === 0
                }
              >
                <Icon name="history" size={13} />
                Reset custom
              </Button>
              <span className="system-prompt__toolbar-hint">
                Drag the grip, or focus it and press Space, then use the arrow
                keys.
              </span>
            </div>

            {listBody}
          </div>
        ) : null}
      </Panel>

      <SystemPromptDialogs
        addOpen={addOpen}
        resetOpen={resetOpen}
        deleteTarget={deleteTarget}
        actionError={actionError}
        sectionCount={sections.length}
        createSaving={createMutation.isPending}
        deleteSaving={deleteMutation.isPending}
        resetSaving={resetMutation.isPending}
        onCloseAdd={() => {
          if (!createMutation.isPending) {
            setAddOpen(false);
            setActionError(null);
          }
        }}
        onCloseDelete={() => {
          if (!deleteMutation.isPending) {
            setDeleteTarget(null);
            setActionError(null);
          }
        }}
        onCloseReset={() => {
          if (!resetMutation.isPending) {
            setResetOpen(false);
            setActionError(null);
          }
        }}
        onCreate={(title, body) => {
          createMutation.mutate({ data: { title, body } });
        }}
        onConfirmDelete={() => {
          if (deleteTarget) {
            deleteMutation.mutate({ sectionId: deleteTarget.id });
          }
        }}
        onConfirmReset={() => resetMutation.mutate()}
      />
    </>
  );
}
