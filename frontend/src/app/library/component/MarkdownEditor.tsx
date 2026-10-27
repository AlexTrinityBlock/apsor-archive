import {
  Suspense,
  forwardRef,
  lazy,
  useCallback,
  useDeferredValue,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PencilLine } from "lucide-react";

import { ApiError } from "../../../apis/fetch-client";
import type { FileSchema } from "../../generated-apis-types/schemas";
import {
  useCreateTextFile,
  useUpdateFileContent,
} from "../../generated-apis-types/files/files";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n, type Translate, type TranslationKey } from "../../i18n";
import { ViewerLoading } from "../../viewer/component/ViewerStates";
import { countLines } from "../../viewer/component/viewer-utils";
import { MarkdownToolbar } from "./MarkdownToolbar";
import { useMarkdownDocument } from "./useMarkdownDocument";
import {
  describeError,
  invalidateLibraryQueries,
  joinArchivePath,
  normalizeArchivePath,
} from "./library-utils";

const MarkdownSheet = lazy(() =>
  import("../../viewer/component/MarkdownSheet").then((module) => ({
    default: module.MarkdownSheet,
  })),
);

export interface MarkdownEditorHandle {
  requestClose: () => void;
}

export interface MarkdownEditorProps {
  readonly mode: "edit" | "new";
  readonly file?: FileSchema;
  readonly defaultDirectory?: string;
  readonly onCancel: () => void;
  readonly onSaved: (file: FileSchema) => void;
  readonly onDirtyChange?: (dirty: boolean) => void;
  readonly onRename?: () => void;
}

type MobilePane = "write" | "preview";

const DEFAULT_NEW_FILE_NAME = "untitled.md";

/** The folder for a new note is fixed while the dialog is open and normalized to
 * an absolute folder path. */
function normalizeNewNoteDirectory(directory: string | undefined): string {
  const normalized = normalizeArchivePath(directory ?? "/");
  return normalized.length === 0 ? "/" : normalized;
}

/** Append `.md` when there is no Markdown extension; other names keep the shape the user typed. */
function ensureMarkdownFileName(rawName: string): string {
  const name = rawName.trim();
  if (name.length === 0) {
    return "";
  }
  const lower = name.toLowerCase();
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) {
    return name;
  }
  return `${name}.md`;
}

/** Control characters (C0, DEL, and C1) must not appear in a file name. */
function hasControlCharacter(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint < 0x20 || (codePoint >= 0x7f && codePoint <= 0x9f)) {
      return true;
    }
  }
  return false;
}

/** Allow a single file name only: not blank, no path separators, and not `.` or `..`. */
function isValidNewFileName(rawName: string): boolean {
  if (hasControlCharacter(rawName)) {
    return false;
  }
  const name = rawName.trim();
  return (
    name.length > 0 &&
    name !== "." &&
    name !== ".." &&
    !name.includes("/") &&
    !name.includes("\\")
  );
}

function countWords(value: string): number {
  const trimmed = value.trim();
  return trimmed.length === 0 ? 0 : trimmed.split(/\s+/u).length;
}

/** A new file compares the name as well as the content; an existing file compares content only. */
function isDocumentDirty(
  mode: "edit" | "new",
  content: string,
  initialContent: string | null,
  fileName: string,
  initialFileName: string,
): boolean {
  if (mode === "new") {
    return content !== (initialContent ?? "") || fileName !== initialFileName;
  }
  return initialContent !== null && content !== initialContent;
}

interface NewNoteLocation {
  readonly invalid: boolean;
  readonly error: string | null;
  readonly prefix: string;
  readonly resolvedPath: string;
}

/** Derive the prefix, the inline error, and the actual path to create from the
 * fixed folder and the file name. */
function resolveNewNoteLocation(
  directory: string,
  fileName: string,
  t: Translate,
): NewNoteLocation {
  const invalid = !isValidNewFileName(fileName);
  return {
    invalid,
    error: invalid ? t("library.editor.fileNameError") : null,
    prefix: directory === "/" ? "/" : `${directory}/`,
    resolvedPath: joinArchivePath(directory, ensureMarkdownFileName(fileName)),
  };
}

function isVersionConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === "file_version_conflict";
}

function isPathConflict(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === "tree_path_conflict" || error.status === 409)
  );
}

interface EditorStatusInput {
  readonly isSaving: boolean;
  readonly loadError: boolean;
  readonly serverError: string | null;
  readonly loading: boolean;
  readonly dirty: boolean;
  readonly isNew: boolean;
}

interface EditorStatus {
  readonly key: TranslationKey;
  readonly className: string;
}

/** Collapse loading, saving, unsaved, and error states into one header chip. */
function resolveEditorStatus({
  isSaving,
  loadError,
  serverError,
  loading,
  dirty,
  isNew,
}: EditorStatusInput): EditorStatus {
  if (isSaving) {
    return { key: "library.editor.saving", className: "is-saving" };
  }
  if (loadError || serverError) {
    return { key: "library.editor.statusError", className: "is-error" };
  }
  if (loading) {
    return { key: "library.editor.loading", className: "is-saving" };
  }
  if (dirty || isNew) {
    return { key: "library.editor.unsaved", className: "is-unsaved" };
  }
  return { key: "library.editor.saved", className: "is-saved" };
}

function saveFailureMessage(
  error: unknown,
  mode: "edit" | "new",
  t: Translate,
): string {
  if (mode === "edit" && isVersionConflict(error)) {
    return t("library.editor.versionConflict");
  }
  if (mode === "new" && isPathConflict(error)) {
    return t("library.editor.pathConflict");
  }
  const detail = describeError(error);
  return detail === t("library.errors.generic")
    ? t("library.editor.saveError")
    : detail;
}

interface NewNotePathFieldProps {
  readonly prefix: string;
  readonly fileName: string;
  readonly error: string | null;
  readonly disabled: boolean;
  readonly onFileNameChange: (nextValue: string) => void;
}

/** The fixed folder prefix for a new note and its single editable file name field. */
function NewNotePathField({
  prefix,
  fileName,
  error,
  disabled,
  onFileNameChange,
}: NewNotePathFieldProps) {
  const { t } = useI18n();
  const fileNameId = useId();
  const errorId = useId();

  return (
    <div className="markdown-editor__path">
      <span className="markdown-editor__path-label">
        {t("library.editor.folderLabel")}
      </span>
      <code className="markdown-editor__path-prefix" title={prefix}>
        {prefix}
      </code>
      <label className="markdown-editor__path-label" htmlFor={fileNameId}>
        {t("library.editor.fileNameLabel")}
      </label>
      <input
        id={fileNameId}
        className="markdown-editor__path-input"
        type="text"
        value={fileName}
        onChange={(event) => onFileNameChange(event.target.value)}
        placeholder={t("library.editor.fileNamePlaceholder")}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
      />
      {error ? (
        <span id={errorId} className="markdown-editor__path-error" role="alert">
          {error}
        </span>
      ) : null}
      <span className="markdown-editor__path-hint">
        {t("library.editor.newNoteDescription")}
      </span>
    </div>
  );
}

interface MarkdownEditorBodyProps {
  readonly ready: boolean;
  readonly loadError: boolean;
  readonly loadErrorMessage: string | null;
  readonly missingFile: boolean;
  readonly retry: () => void;
  readonly content: string;
  readonly onContentChange: (nextValue: string) => void;
  readonly textareaRef: RefObject<HTMLTextAreaElement | null>;
  readonly isSaving: boolean;
  readonly deferredContent: string;
  readonly mobilePane: MobilePane;
}

function MarkdownEditorBody({
  ready,
  loadError,
  loadErrorMessage,
  missingFile,
  retry,
  content,
  onContentChange,
  textareaRef,
  isSaving,
  deferredContent,
  mobilePane,
}: MarkdownEditorBodyProps) {
  const { t } = useI18n();

  if (!ready) {
    if (!loadError) {
      return (
        <div className="markdown-editor__state">
          <ViewerLoading label={t("library.editor.loading")} />
        </div>
      );
    }
    return (
      <div className="markdown-editor__state">
        <div className="markdown-editor__state-card" role="alert">
          <Icon name="info" size={22} />
          <h3>{t("library.editor.loadError")}</h3>
          <p>{loadErrorMessage ?? t("library.editor.loadError")}</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={retry}
            disabled={missingFile}
          >
            <Icon name="history" size={15} />
            {t("library.common.retry")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="markdown-editor__panes" data-mobile-pane={mobilePane}>
      <section className="markdown-editor__pane markdown-editor__pane--write">
        <textarea
          ref={textareaRef}
          className="markdown-editor__textarea"
          value={content}
          onChange={(event) => onContentChange(event.target.value)}
          aria-label={t("library.editor.write")}
          spellCheck={false}
          disabled={isSaving}
          data-autofocus
        />
      </section>

      <section
        className="markdown-editor__pane markdown-editor__pane--preview"
        aria-label={t("library.editor.readMode")}
      >
        <div className="markdown-editor__preview">
          <Suspense
            fallback={
              <p className="markdown-editor__preview-loading">
                {t("library.viewer.loading.markdown")}
              </p>
            }
          >
            <MarkdownSheet content={deferredContent} />
          </Suspense>
        </div>
      </section>
    </div>
  );
}

interface EditorTitleProps {
  readonly mode: MarkdownEditorProps["mode"];
  readonly file: FileSchema | undefined;
  readonly isSaving: boolean;
  readonly onRename: (() => void) | undefined;
}

/**
 * The file name in the header: a rename button is attached when editing an
 * existing file, otherwise only the title is shown.
 */
function EditorTitle({ mode, file, isSaving, onRename }: EditorTitleProps) {
  const { t } = useI18n();
  if (mode !== "edit" || !file || !onRename) {
    return (
      <h2 className="markdown-editor__title">
        {file ? file.file_name : t("library.editor.newNoteTitle")}
      </h2>
    );
  }
  return (
    <div className="markdown-editor__title-row">
      <h2 className="markdown-editor__title">{file.file_name}</h2>
      <button
        type="button"
        className="markdown-editor__rename"
        onClick={onRename}
        disabled={isSaving}
        aria-label={t("library.common.rename")}
        title={t("library.common.rename")}
      >
        <PencilLine size={13} strokeWidth={1.7} aria-hidden="true" />
      </button>
    </div>
  );
}

interface ChunkReconstructionNoteProps {
  readonly mode: MarkdownEditorProps["mode"];
  readonly usingChunks: boolean;
}

/**
 * Editing warning for a chunk-only file: the content is rebuilt from index
 * segments, so saving may normalize whitespace. It is only shown when editing an
 * existing file that uses chunks, and it never blocks saving.
 */
function ChunkReconstructionNote({
  mode,
  usingChunks,
}: ChunkReconstructionNoteProps) {
  const { t } = useI18n();

  if (mode !== "edit" || !usingChunks) {
    return null;
  }

  return (
    <div className="markdown-editor__reconstruction" role="note">
      <Icon name="info" size={16} />
      <p>{t("library.editor.chunkWarning")}</p>
    </div>
  );
}

/**
 * The Markdown editor itself: header, formatting toolbar, side-by-side writing
 * and preview, plus word count and save actions. An existing file goes through a
 * versioned update, while a new note uses the synchronous create endpoint.
 */
export const MarkdownEditor = forwardRef<MarkdownEditorHandle, MarkdownEditorProps>(
  function MarkdownEditor(
    {
      mode,
      file,
      defaultDirectory,
      onCancel,
      onSaved,
      onDirtyChange,
      onRename,
    },
    ref,
  ) {
    const { t, formatNumber } = useI18n();
    const queryClient = useQueryClient();
    const toast = useToast();
    const discardBodyId = useId();
    const rootRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const initializedRef = useRef(mode === "new");
    const focusedRef = useRef(false);

    const [fixedDirectory] = useState(() =>
      normalizeNewNoteDirectory(defaultDirectory),
    );
    const [fileName, setFileName] = useState(DEFAULT_NEW_FILE_NAME);
    const [content, setContent] = useState("");
    const [initialContent, setInitialContent] = useState<string | null>(
      mode === "new" ? "" : null,
    );
    const [mobilePane, setMobilePane] = useState<MobilePane>("write");
    const [discardOpen, setDiscardOpen] = useState(false);
    const [serverError, setServerError] = useState<string | null>(null);

    const markdownDocument = useMarkdownDocument(
      mode === "edit" ? file : undefined,
    );
    const deferredContent = useDeferredValue(content);

    const updateMutation = useUpdateFileContent();
    const createMutation = useCreateTextFile();
    const isSaving = updateMutation.isPending || createMutation.isPending;

    // The document content loads asynchronously; the initial snapshot is only
    // taken when content first arrives so a load is not mistaken for a user edit,
    // and a later refetch cannot overwrite a draft that is being changed.
    /* eslint-disable react-hooks/set-state-in-effect */
    useEffect(() => {
      if (mode !== "edit" || initializedRef.current) {
        return;
      }
      if (markdownDocument.content === null) {
        return;
      }
      initializedRef.current = true;
      setContent(markdownDocument.content);
      setInitialContent(markdownDocument.content);
    }, [markdownDocument.content, mode]);
    /* eslint-enable react-hooks/set-state-in-effect */

    const dirty = isDocumentDirty(
      mode,
      content,
      initialContent,
      fileName,
      DEFAULT_NEW_FILE_NAME,
    );

    useEffect(() => {
      onDirtyChange?.(dirty);
    }, [dirty, onDirtyChange]);

    useEffect(() => {
      return () => {
        onDirtyChange?.(false);
      };
    }, [onDirtyChange]);

    useEffect(() => {
      if (!dirty) {
        return;
      }
      const handleBeforeUnload = (event: BeforeUnloadEvent) => {
        event.preventDefault();
        event.returnValue = "";
      };
      window.addEventListener("beforeunload", handleBeforeUnload);
      return () => window.removeEventListener("beforeunload", handleBeforeUnload);
    }, [dirty]);

    const missingFile = mode === "edit" && file === undefined;
    const loadError =
      missingFile || (mode === "edit" && markdownDocument.error !== null);
    const editorReady =
      mode === "new" ||
      (!missingFile &&
        initialContent !== null &&
        !markdownDocument.loading &&
        markdownDocument.error === null);

    const newNoteLocation = resolveNewNoteLocation(fixedDirectory, fileName, t);
    const resolvedPath = newNoteLocation.resolvedPath;
    const normalizedContent = content.trim();
    const canSave =
      editorReady &&
      !isSaving &&
      dirty &&
      normalizedContent.length > 0 &&
      (mode === "new"
        ? !newNoteLocation.invalid && newNoteLocation.resolvedPath.length > 1
        : file !== undefined);

    useEffect(() => {
      if (!editorReady || focusedRef.current) {
        return;
      }
      focusedRef.current = true;
      textareaRef.current?.focus({ preventScroll: true });
    }, [editorReady]);

    const saveExistingFile = useCallback(async () => {
      if (!file) {
        return;
      }
      const updatedFile = await updateMutation.mutateAsync({
        fileId: file.id,
        data: {
          content,
          expected_version: file.version,
        },
      });
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        search: true,
        fileIds: [file.id, updatedFile.id],
      });
      void queryClient.invalidateQueries({ queryKey: ["/api/v1/files"] });
      setInitialContent(content);
      toast.success(
        t("library.editor.savedToast", {
          name: updatedFile.file_name,
          version: updatedFile.version,
        }),
      );
      onSaved(updatedFile);
    }, [content, file, onSaved, queryClient, t, toast, updateMutation]);

    const saveNewFile = useCallback(async () => {
      const createdFile = await createMutation.mutateAsync({
        data: {
          path: resolvedPath,
          content,
        },
      });
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        search: true,
        fileIds: [createdFile.id],
      });
      void queryClient.invalidateQueries({ queryKey: ["/api/v1/files"] });
      setInitialContent(content);
      toast.success(
        t("library.editor.createdToast", { name: createdFile.file_name }),
      );
      onSaved(createdFile);
    }, [
      content,
      createMutation,
      onSaved,
      queryClient,
      resolvedPath,
      t,
      toast,
    ]);

    const handleSave = useCallback(async () => {
      if (!canSave) {
        return;
      }
      setServerError(null);
      try {
        if (mode === "new") {
          await saveNewFile();
        } else {
          await saveExistingFile();
        }
      } catch (error) {
        setServerError(saveFailureMessage(error, mode, t));
      }
    }, [canSave, mode, saveExistingFile, saveNewFile, t]);

    const requestClose = useCallback(() => {
      if (isSaving) {
        return;
      }
      if (dirty) {
        setDiscardOpen(true);
        return;
      }
      onCancel();
    }, [dirty, isSaving, onCancel]);

    useImperativeHandle(ref, () => ({ requestClose }), [requestClose]);

    const handleDiscard = () => {
      setDiscardOpen(false);
      onCancel();
    };

    useEffect(() => {
      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.defaultPrevented) {
          return;
        }
        // While an outer library dialog (for example a rename opened from the
        // header) holds focus, it owns the shortcuts and Escape, so the editor is
        // not closed at the same time.
        const editorRoot = rootRef.current;
        const dialogLayer = document.querySelector(".library-dialog-layer");
        if (dialogLayer && editorRoot && !dialogLayer.contains(editorRoot)) {
          return;
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          void handleSave();
          return;
        }
        if (event.key !== "Escape") {
          return;
        }
        event.preventDefault();
        if (discardOpen) {
          setDiscardOpen(false);
          return;
        }
        requestClose();
      };
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }, [discardOpen, handleSave, requestClose]);

    const status = resolveEditorStatus({
      isSaving,
      loadError,
      serverError,
      loading: markdownDocument.loading,
      dirty,
      isNew: mode === "new",
    });

    const wordCount = countWords(content);
    const lineCount = countLines(content);

    return (
      <div className="markdown-editor" ref={rootRef}>
        <header className="markdown-editor__head">
          <div className="markdown-editor__identity">
            <p className="eyebrow">
              {mode === "new"
                ? t("library.editor.newNoteTitle")
                : t("library.editor.editing")}
            </p>
            <EditorTitle
              mode={mode}
              file={file}
              isSaving={isSaving}
              onRename={onRename}
            />
            {mode === "edit" && file ? (
              <code className="markdown-editor__file-path">
                {file.raw_file_path}
              </code>
            ) : null}
            {mode === "edit" && markdownDocument.usingChunks ? (
              <span className="markdown-editor__source-note">
                {t("library.viewer.text.indexedChunks")}
              </span>
            ) : null}
          </div>

          <div className="markdown-editor__head-side">
            <div
              className="markdown-editor__view-toggle"
              role="group"
              aria-label={t("library.editor.preview")}
            >
              <button
                type="button"
                className={
                  mobilePane === "write"
                    ? "markdown-editor__view-button is-active"
                    : "markdown-editor__view-button"
                }
                aria-pressed={mobilePane === "write"}
                onClick={() => setMobilePane("write")}
              >
                {t("library.editor.write")}
              </button>
              <button
                type="button"
                className={
                  mobilePane === "preview"
                    ? "markdown-editor__view-button is-active"
                    : "markdown-editor__view-button"
                }
                aria-pressed={mobilePane === "preview"}
                onClick={() => setMobilePane("preview")}
              >
                {t("library.editor.preview")}
              </button>
            </div>

            <span className={`markdown-editor__status ${status.className}`}>
              {t(status.key)}
            </span>

            <button
              type="button"
              className="markdown-editor__close"
              onClick={requestClose}
              aria-label={t("library.editor.closeEditor")}
              title={t("library.editor.closeEditor")}
              disabled={isSaving}
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        </header>

        <ChunkReconstructionNote
          mode={mode}
          usingChunks={markdownDocument.usingChunks}
        />

        {mode === "new" ? (
          <NewNotePathField
            prefix={newNoteLocation.prefix}
            fileName={fileName}
            error={newNoteLocation.error}
            disabled={isSaving}
            onFileNameChange={setFileName}
          />
        ) : null}

        <MarkdownToolbar
          textareaRef={textareaRef}
          value={content}
          onChange={setContent}
          disabled={isSaving || !editorReady}
        />

        <MarkdownEditorBody
          ready={editorReady}
          loadError={loadError}
          loadErrorMessage={
            markdownDocument.error
              ? describeError(markdownDocument.error)
              : null
          }
          missingFile={missingFile}
          retry={markdownDocument.retry}
          content={content}
          onContentChange={setContent}
          textareaRef={textareaRef}
          isSaving={isSaving}
          deferredContent={deferredContent}
          mobilePane={mobilePane}
        />

        {discardOpen ? (
          <div
            className="markdown-editor__discard"
            role="alertdialog"
            aria-label={t("library.editor.discardTitle")}
            aria-describedby={discardBodyId}
          >
            <div className="markdown-editor__discard-copy">
              <strong>{t("library.editor.discardTitle")}</strong>
              <p id={discardBodyId}>{t("library.editor.discardBody")}</p>
            </div>
            <div className="markdown-editor__discard-actions">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDiscardOpen(false)}
              >
                {t("library.editor.keepEditing")}
              </Button>
              <Button variant="danger" size="sm" onClick={handleDiscard}>
                {t("library.editor.discardConfirm")}
              </Button>
            </div>
          </div>
        ) : null}

        {serverError ? (
          <div className="markdown-editor__error" role="alert">
            <Icon name="info" size={15} />
            <span>{serverError}</span>
          </div>
        ) : null}

        <footer className="markdown-editor__foot">
          <div className="markdown-editor__stats">
            <span>
              {t("library.editor.words", { count: formatNumber(wordCount) })}
            </span>
            <span aria-hidden="true">·</span>
            <span>
              {t("library.editor.characters", {
                count: formatNumber(content.length),
              })}
            </span>
            <span aria-hidden="true">·</span>
            <span>
              {t("library.editor.lines", { count: formatNumber(lineCount) })}
            </span>
            {normalizedContent.length === 0 ? (
              <span className="markdown-editor__hint">
                {t("library.editor.emptyContent")}
              </span>
            ) : null}
          </div>

          <div className="markdown-editor__actions">
            <Button
              variant="ghost"
              size="sm"
              onClick={requestClose}
              disabled={isSaving}
            >
              {t("library.common.cancel")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleSave()}
              disabled={!canSave}
              title={
                normalizedContent.length === 0
                  ? t("library.editor.emptyContent")
                  : undefined
              }
            >
              {isSaving
                ? t("library.editor.saving")
                : t("library.editor.save")}
              <Icon name="check" size={15} />
            </Button>
          </div>
        </footer>
      </div>
    );
  },
);
