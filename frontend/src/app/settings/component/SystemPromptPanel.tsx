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
  getListSystemPromptSectionsQueryKey,
  useCreateSystemPromptSection,
  useDeleteSystemPromptSection,
  useListSystemPromptSections,
  useReorderSystemPromptSections,
  useResetSystemPromptSections,
  useUpdateSystemPromptSection,
} from "../../generated-apis-types";
import type {
  ListResponseSchemaSystemPromptSectionReadSchema,
  SystemPromptSectionReadSchema,
} from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { apiErrorMessage } from "./settings-utils";
import { SettingsDialog } from "./SettingsDialog";

type SectionList = ListResponseSchemaSystemPromptSectionReadSchema;

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

const TRAILING_ORDER = [
  "systemPrompt.panel.order.userProfile",
  "systemPrompt.panel.order.toolCatalog",
  "systemPrompt.panel.order.conversationMessages",
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
  const { t, formatDateTime, formatNumber } = useI18n();
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
          {t("systemPrompt.editor.title")}
        </label>
        <input
          ref={titleRef}
          id={titleId}
          className="input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={200}
          placeholder={t("systemPrompt.editor.titlePlaceholder")}
          disabled={saving}
        />
        <span className="field-help">
          {t("systemPrompt.editor.titleHelp")}
        </span>
      </div>

      <div className="field system-prompt-section__field">
        <label className="field-label" htmlFor={bodyId}>
          {t("systemPrompt.editor.body")}
        </label>
        <textarea
          id={bodyId}
          className="textarea system-prompt-section__textarea"
          value={body}
          onChange={(event) => setBody(event.target.value)}
          maxLength={32_000}
          rows={10}
          placeholder={t("systemPrompt.editor.bodyPlaceholder")}
          disabled={saving}
        />
        <span className="field-help system-prompt__count">
          {t("systemPrompt.editor.count", {
            count: formatNumber(body.length),
          })}
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
          {saving ? t("systemPrompt.editor.saving") : t("systemPrompt.editor.save")}
        </Button>
        <Button
          type="button"
          variant="danger"
          size="sm"
          onClick={onRequestDelete}
          disabled={saving}
        >
          <Icon name="trash" size={14} />
          {t("systemPrompt.editor.delete")}
        </Button>
        <span className="system-prompt__meta">
          {t("systemPrompt.editor.updated", {
            date: formatDateTime(section.updated_at),
          })}
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
  const { t, formatNumber } = useI18n();
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
          aria-label={t("systemPrompt.section.reorderAria", {
            title: section.title,
          })}
          title={t("systemPrompt.section.reorderTitle")}
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
            {t(
              section.body.length === 1
                ? "systemPrompt.section.charactersOne"
                : "systemPrompt.section.charactersOther",
              { count: formatNumber(section.body.length) },
            )}
          </span>
        </div>

        <div className="system-prompt-section__actions">
          <button
            type="button"
            className="system-prompt__collapse system-prompt-section__toggle"
            aria-expanded={open}
            aria-controls={open ? bodyId : undefined}
            onClick={() => setOpenState(!open)}
            title={
              open
                ? t("systemPrompt.section.collapseTitle")
                : t("systemPrompt.section.expandTitle")
            }
          >
            <Icon name={open ? "chevron-down" : "chevron-right"} size={13} />
            <span>
              {open
                ? t("systemPrompt.section.collapse")
                : t("systemPrompt.section.expand")}
            </span>
          </button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleEdit}
            disabled={saving}
          >
            <Icon name="pencil" size={13} />
            {t("systemPrompt.section.edit")}
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={onRequestDelete}
            disabled={saving}
          >
            <Icon name="trash" size={13} />
            {t("systemPrompt.section.delete")}
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
  const { t } = useI18n();
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
          aria-label={t("systemPrompt.panel.sectionsAria")}
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

/** The provider-facing order: every section, then the frozen tool snapshot. */
function ProviderOrderBlock({ sections }: ProviderOrderProps) {
  const { t } = useI18n();
  const orderItems = [
    ...sections.map((section) => ({
      key: `section-${section.id}`,
      label: section.title,
      section: true,
    })),
    ...TRAILING_ORDER.map((key) => ({
      key: `trailing-${key}`,
      label: t(key),
      section: false,
    })),
  ];

  return (
    <div className="system-prompt__order-block">
      <p className="mono-label">{t("systemPrompt.panel.order.heading")}</p>
      <ol
        className="system-prompt__order"
        aria-label={t("systemPrompt.panel.order.ariaLabel")}
      >
        {orderItems.map((item, index) => (
          <li
            key={item.key}
            className={[
              index === 0 ? "is-first" : null,
              item.section ? "is-custom" : null,
            ]
              .filter(Boolean)
              .join(" ") || undefined}
          >
            <span className="system-prompt__order-index">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="system-prompt__order-label">{item.label}</span>
            {item.section ? (
              <span className="system-prompt__order-tag">
                {t("systemPrompt.panel.order.promptTag")}
              </span>
            ) : null}
          </li>
        ))}
      </ol>
      <p className="settings-hint">{t("systemPrompt.panel.order.hint")}</p>
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
  const { t, formatNumber } = useI18n();
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
      setFormError(t("systemPrompt.add.titleRequired"));
      return;
    }
    const trimmedBody = body.trim();
    if (trimmedBody.length === 0) {
      setFormError(t("systemPrompt.add.bodyRequired"));
      return;
    }
    setFormError(null);
    onSubmit(trimmedTitle, trimmedBody);
  };

  return (
    <SettingsDialog
      eyebrow={t("systemPrompt.add.eyebrow")}
      title={t("systemPrompt.add.title")}
      description={t("systemPrompt.add.description")}
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
            {t("systemPrompt.add.cancel")}
          </Button>
          <Button
            type="submit"
            form={formId}
            variant="ink"
            size="sm"
            disabled={saving}
          >
            {saving
              ? t("systemPrompt.add.submitting")
              : t("systemPrompt.add.submit")}
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
          <span className="field-label">{t("systemPrompt.add.titleLabel")}</span>
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
            placeholder={t("systemPrompt.editor.titlePlaceholder")}
            disabled={saving}
            data-autofocus
          />
          <span className="field-help">{t("systemPrompt.add.titleHelp")}</span>
        </label>

        <label className="field" htmlFor={bodyId}>
          <span className="field-label">{t("systemPrompt.add.bodyLabel")}</span>
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
            placeholder={t("systemPrompt.add.bodyPlaceholder")}
            disabled={saving}
          />
          <span className="field-help system-prompt__count">
            {t("systemPrompt.add.count", {
              count: formatNumber(body.length),
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
  const { t } = useI18n();
  return (
    <SettingsDialog
      eyebrow={t("systemPrompt.delete.eyebrow")}
      title={t("systemPrompt.delete.title")}
      description={t("systemPrompt.delete.description", {
        title: target.title,
      })}
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
            {t("systemPrompt.delete.cancel")}
          </Button>
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={onConfirm}
            disabled={saving}
          >
            {saving
              ? t("systemPrompt.delete.deleting")
              : t("systemPrompt.delete.confirm")}
          </Button>
        </>
      }
    >
      <p className="settings-lede">{t("systemPrompt.delete.copy")}</p>
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

/** Confirm restoration of the four seeded defaults. */
function ResetSectionsDialog({
  count,
  saving,
  error,
  onClose,
  onConfirm,
}: ResetDialogProps) {
  const { t } = useI18n();
  let confirmLabel = t(
    count === 1 ? "systemPrompt.reset.confirmOne" : "systemPrompt.reset.confirmOther",
    { count },
  );
  if (saving) {
    confirmLabel = t("systemPrompt.reset.resetting");
  }

  return (
    <SettingsDialog
      eyebrow={t("systemPrompt.reset.eyebrow")}
      title={t("systemPrompt.reset.title")}
      description={t("systemPrompt.reset.description")}
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
            {t("systemPrompt.reset.cancel")}
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
      <p className="settings-lede">{t("systemPrompt.reset.copy")}</p>
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
  const { t } = useI18n();
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
        toast.success(t("systemPrompt.toast.created"));
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
        toast.success(t("systemPrompt.toast.saved"));
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
        toast.success(t("systemPrompt.toast.deleted"));
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
        toast.success(t("systemPrompt.toast.reset"));
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

/** One ordered system prompt collection, frozen per conversation. */
export function SystemPromptPanel() {
  const { t } = useI18n();
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

  const countLabel = t(
    sections.length === 1
      ? "systemPrompt.panel.sectionCountOne"
      : "systemPrompt.panel.sectionCountOther",
    { count: sections.length },
  );
  let countBadge = <Badge tone="neutral">{countLabel}</Badge>;
  if (query.isPending) {
    countBadge = (
      <Badge tone="neutral">{t("systemPrompt.panel.loading")}</Badge>
    );
  } else if (query.isError) {
    countBadge = (
      <Badge tone="vermilion">{t("systemPrompt.panel.unavailable")}</Badge>
    );
  } else if (sections.length > 0) {
    countBadge = <Badge tone="moss">{countLabel}</Badge>;
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
          <strong>{t("systemPrompt.panel.error.title")}</strong>
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
              ? t("systemPrompt.panel.error.retrying")
              : t("systemPrompt.panel.error.retry")}
          </Button>
        </div>
      </div>
    );
  } else if (sections.length === 0) {
    listBody = (
      <div className="system-prompt-empty">
        <p className="system-prompt-empty__copy">
          {t("systemPrompt.panel.empty.copy")}
        </p>
        <Button type="button" variant="ink" size="sm" onClick={openCreate}>
          <Icon name="plus" size={13} />
          {t("systemPrompt.panel.empty.addFirst")}
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
            <Icon name="layers" size={16} />
            {t("systemPrompt.panel.title")}
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
              title={
                open
                  ? t("systemPrompt.panel.collapseTitle")
                  : t("systemPrompt.panel.expandTitle")
              }
            >
              <Icon name={open ? "chevron-down" : "chevron-right"} size={14} />
              <span>
                {open
                  ? t("systemPrompt.panel.collapse")
                  : t("systemPrompt.panel.expand")}
              </span>
            </button>
          </div>
        }
      >
        {open ? (
          <div id="system-prompt-body" className="system-prompt">
            <p className="settings-lede">
              {t("systemPrompt.panel.intro")}
            </p>

            <ProviderOrderBlock sections={sections} />

            <div className="system-prompt__group-head">
              <div>
                <p className="eyebrow">
                  {t("systemPrompt.panel.group.eyebrow")}
                </p>
                <h3>{t("systemPrompt.panel.group.title")}</h3>
              </div>
              <p className="system-prompt__group-lede">
                {t("systemPrompt.panel.group.lede")}
              </p>
            </div>

            <div className="system-prompt__toolbar">
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={openCreate}
                disabled={query.isPending || query.isError}
              >
                <Icon name="plus" size={13} />
                {t("systemPrompt.panel.toolbar.add")}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  setActionError(null);
                  setResetOpen(true);
                }}
                disabled={query.isPending || query.isError || busy}
              >
                <Icon name="history" size={13} />
                {t("systemPrompt.panel.toolbar.reset")}
              </Button>
              <span className="system-prompt__toolbar-hint">
                {t("systemPrompt.panel.toolbar.hint")}
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
