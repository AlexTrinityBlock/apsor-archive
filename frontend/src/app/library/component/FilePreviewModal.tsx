import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { UseQueryResult } from "@tanstack/react-query";

import type {
  FileChunksSchema,
  FileSchema,
  HTTPValidationError,
} from "../../generated-apis-types/schemas";
import { useGetFile, useReadFile } from "../../generated-apis-types/files/files";
import { formatBytes } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import { translateApiError } from "../../i18n/errors";
import { useI18n } from "../../i18n";
import { useScrollLock } from "../../hook/useScrollLock";
import { FileRenderer } from "../../viewer/component/FileViewer";
import { ViewerErrorState, ViewerLoading } from "../../viewer/component/ViewerStates";
import {
  classifyFile,
  fileDownloadUrl,
  kindLabel,
} from "../../viewer/component/viewer-utils";
import {
  MarkdownEditor,
  type MarkdownEditorHandle,
} from "./MarkdownEditor";
import {
  clampChunk,
  isNotFoundError,
  type FileOperationTarget,
} from "./library-utils";

type PreviewTab = "page" | "chunk" | "meta";

interface FilePreviewModalProps {
  readonly fileId: number;
  readonly requestedChunk: number;
  readonly startInEdit?: boolean;
  readonly onClose: () => void;
  readonly onChunkChange: (chunk: number) => void;
  readonly onFileVersionChange: (nextFileId: number) => void;
  readonly onEditModeChange?: (editing: boolean) => void;
  readonly onMove: (target: FileOperationTarget) => void;
  readonly onCopy: (target: FileOperationTarget) => void;
  readonly onRename: (target: FileOperationTarget) => void;
  readonly onDelete: (target: FileOperationTarget) => void;
}

interface PreviewBodyProps {
  readonly fileId: number;
  readonly fileQuery: ReturnType<typeof useGetFile>;
  readonly file: FileSchema | undefined;
  readonly activeTab: PreviewTab;
  readonly requestedChunk: number;
  readonly effectiveChunk: number;
  readonly chunkQuery: UseQueryResult<FileChunksSchema, HTTPValidationError>;
  readonly onChunkChange: (chunk: number) => void;
  readonly onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const PREVIEW_TABS: readonly {
  readonly id: PreviewTab;
  readonly labelKey:
    | "library.preview.pageTab"
    | "library.preview.chunkTab"
    | "library.preview.metaTab";
}[] = [
  { id: "page", labelKey: "library.preview.pageTab" },
  { id: "chunk", labelKey: "library.preview.chunkTab" },
  { id: "meta", labelKey: "library.preview.metaTab" },
];

function fileState(file: FileSchema): {
  readonly labelKey:
    | "library.preview.stateDeleted"
    | "library.preview.stateHistory"
    | "library.preview.stateCurrent";
  readonly tone: "moss" | "ochre" | "vermilion";
} {
  if (file.deleted_at) {
    return { labelKey: "library.preview.stateDeleted", tone: "vermilion" };
  }
  if (!file.is_current) {
    return { labelKey: "library.preview.stateHistory", tone: "ochre" };
  }
  return { labelKey: "library.preview.stateCurrent", tone: "moss" };
}

function operationTarget(file: FileSchema): FileOperationTarget {
  return {
    file_id: file.id,
    file_name: file.file_name,
    raw_file_path: file.raw_file_path,
  };
}

function MetaItem({
  label,
  value,
  wide = false,
}: {
  readonly label: string;
  readonly value: ReactNode;
  readonly wide?: boolean;
}) {
  return (
    <div className={wide ? "meta-item library-preview__meta-wide" : "meta-item"}>
      <dt className="meta-key">{label}</dt>
      <dd className="meta-value">{value}</dd>
    </div>
  );
}

function MissingPreview({
  fileId,
  onClose,
}: {
  readonly fileId: number;
  readonly onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="library-preview__status">
      <span className="library-preview__status-mark" aria-hidden="true">
        <Icon name="info" size={22} />
      </span>
      <p className="eyebrow">{t("library.preview.missingEyebrow")}</p>
      <h3>{t("library.preview.missingTitle")}</h3>
      <p>
        {t("library.preview.missingDescription", { id: fileId })}
      </p>
      <Button variant="secondary" size="sm" onClick={onClose}>
        {t("library.common.closePreview")}
      </Button>
    </div>
  );
}

function FileStateNotice({ file }: { readonly file: FileSchema }) {
  const { t } = useI18n();
  if (!file.deleted_at && file.is_current) {
    return null;
  }
  return (
    <div className="viewer-notice viewer-notice--history" role="note">
      <Icon name="history" size={16} />
      <p>
        {file.deleted_at
          ? t("library.preview.softDeletedNotice")
          : t("library.preview.supersededNotice")}
      </p>
    </div>
  );
}

function ChunkResults({
  chunkQuery,
}: {
  readonly chunkQuery: UseQueryResult<FileChunksSchema, HTTPValidationError>;
}) {
  const { t, formatNumber } = useI18n();
  if (chunkQuery.isLoading) {
    return <ViewerLoading label={t("library.preview.chunkLoading")} />;
  }
  if (chunkQuery.error) {
    return (
      <ViewerErrorState
        error={chunkQuery.error}
        title={t("library.preview.chunkErrorTitle")}
        onRetry={() => void chunkQuery.refetch()}
      />
    );
  }
  if (!chunkQuery.data || chunkQuery.data.chunks.length === 0) {
    return (
      <p className="library-preview__chunk-empty-text">{t("library.preview.chunkEmpty")}</p>
    );
  }
  return (
    <div className="library-preview__chunk-list">
      {chunkQuery.data.chunks.map((chunk) => (
        <article className="library-preview__chunk" key={chunk.chunk}>
          <header className="library-preview__chunk-head">
            <span className="library-preview__chunk-index">#{chunk.chunk}</span>
            <span className="library-preview__chunk-meta">
              {t("library.preview.chunkMeta", {
                chars: formatNumber(chunk.char_count),
                tokens: formatNumber(chunk.token_count),
              })}
            </span>
            {chunk.is_current ? null : (
              <Badge tone="ochre">{t("library.preview.stateHistory")}</Badge>
            )}
            <CopyButton
              value={chunk.content}
              label={t("library.preview.copyChunk")}
              iconOnly
              title={t("library.preview.copyChunkTitle", { chunk: chunk.chunk })}
            />
          </header>
          <pre className="library-preview__chunk-body">{chunk.content}</pre>
        </article>
      ))}
    </div>
  );
}

function ChunkInspection({
  file,
  requestedChunk,
  effectiveChunk,
  onChunkChange,
  chunkQuery,
}: {
  readonly file: FileSchema;
  readonly requestedChunk: number;
  readonly effectiveChunk: number;
  readonly onChunkChange: (chunk: number) => void;
  readonly chunkQuery: UseQueryResult<FileChunksSchema, HTTPValidationError>;
}) {
  const { t, formatNumber } = useI18n();
  if (file.total_chunks === 0) {
    return (
      <div className="library-preview__chunk-empty">
        <Icon name="layers" size={22} />
        <h3>{t("library.preview.noChunksTitle")}</h3>
        <p>{t("library.preview.noChunksDescription")}</p>
      </div>
    );
  }

  return (
    <div className="library-preview__chunks">
      <div className="library-preview__chunkbar">
        <div className="library-preview__chunknav">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onChunkChange(effectiveChunk - 1)}
            disabled={effectiveChunk <= 1 || chunkQuery.isFetching}
          >
            <Icon name="arrow-right" size={14} className="library-preview__back-icon" />
            {t("library.common.previous")}
          </Button>
          <span className="library-preview__chunk-position">
            #{effectiveChunk} / {formatNumber(file.total_chunks)}
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onChunkChange(effectiveChunk + 1)}
            disabled={effectiveChunk >= file.total_chunks || chunkQuery.isFetching}
          >
            {t("library.common.next")}
            <Icon name="arrow-right" size={14} />
          </Button>
        </div>
        <span className="library-preview__chunk-hint">
          {t("library.preview.chunkIndexHint")}
        </span>
      </div>

      {requestedChunk !== effectiveChunk ? (
        <p className="library-preview__clamp" role="status">
          {t("library.preview.clampNotice", {
            requested: requestedChunk,
            total: formatNumber(file.total_chunks),
            effective: effectiveChunk,
          })}
        </p>
      ) : null}

      <ChunkResults chunkQuery={chunkQuery} />
    </div>
  );
}

function PagePreview({
  file,
  isImage,
}: {
  readonly file: FileSchema;
  readonly isImage: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="library-preview__stage">
      <FileStateNotice file={file} />
      <FileRenderer file={file} />
      {isImage && (file.ai_summary || file.ai_tags.length > 0) ? (
        <div className="library-preview__caption">
          {file.ai_summary ? (
            <div>
              <p className="eyebrow">{t("library.preview.summary")}</p>
              <p className="prose-text">{file.ai_summary}</p>
            </div>
          ) : null}
          {file.ai_tags.length > 0 ? (
            <ul className="library-preview__tags">
              {file.ai_tags.map((tag, index) => (
                <li key={`${tag}-${index}`}>{tag}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function MetadataPanel({ file }: { readonly file: FileSchema }) {
  const { t, formatDateTime, formatNumber } = useI18n();
  return (
    <div className="library-preview__metadata">
      <dl className="meta-grid library-preview__meta">
        <MetaItem label={t("library.preview.meta.fileName")} value={file.file_name} />
        <MetaItem label={t("library.preview.meta.fileId")} value={`#${file.id}`} />
        <MetaItem label={t("library.preview.meta.path")} value={file.raw_file_path} wide />
        <MetaItem
          label={t("library.preview.meta.mimeType")}
          value={file.mime_type || "—"}
        />
        <MetaItem
          label={t("library.preview.meta.extension")}
          value={file.extension ? file.extension.toUpperCase() : "—"}
        />
        <MetaItem
          label={t("library.preview.meta.documentType")}
          value={file.document_type || "—"}
        />
        <MetaItem label={t("library.preview.meta.version")} value={`v${file.version}`} />
        <MetaItem
          label={t("library.preview.meta.current")}
          value={file.is_current ? t("library.preview.yes") : t("library.preview.no")}
        />
        <MetaItem label={t("library.preview.meta.size")} value={formatBytes(file.size_bytes)} />
        <MetaItem
          label={t("library.preview.meta.indexedChunks")}
          value={formatNumber(file.total_chunks)}
        />
        <MetaItem
          label={t("library.preview.meta.originalStored")}
          value={file.has_original ? t("library.preview.yes") : t("library.preview.no")}
        />
        <MetaItem
          label={t("library.preview.meta.supersedes")}
          value={
            file.supersedes_file_id !== null
              ? t("library.preview.fileIdFallback", { id: file.supersedes_file_id })
              : "—"
          }
        />
        <MetaItem
          label={t("library.preview.meta.created")}
          value={formatDateTime(file.created_at)}
        />
        <MetaItem
          label={t("library.preview.meta.updated")}
          value={formatDateTime(file.updated_at)}
        />
        {file.deleted_at ? (
          <MetaItem
            label={t("library.preview.meta.deleted")}
            value={formatDateTime(file.deleted_at)}
          />
        ) : null}
        {file.ai_summary ? (
          <MetaItem
            label={t("library.preview.meta.summary")}
            value={<span className="library-preview__meta-text">{file.ai_summary}</span>}
            wide
          />
        ) : null}
        {file.ai_tags.length > 0 ? (
          <MetaItem
            label={t("library.preview.meta.tags")}
            value={
              <ul className="library-preview__tags">
                {file.ai_tags.map((tag, index) => (
                  <li key={`${tag}-${index}`}>{tag}</li>
                ))}
              </ul>
            }
            wide
          />
        ) : null}
      </dl>
      <p className="library-preview__meta-note">
        {t("library.preview.metaNote")}
      </p>
    </div>
  );
}

function PreviewBody({
  fileId,
  fileQuery,
  file,
  activeTab,
  requestedChunk,
  effectiveChunk,
  chunkQuery,
  onChunkChange,
  onClose,
}: PreviewBodyProps) {
  const { t } = useI18n();
  if (fileQuery.isLoading) {
    return <ViewerLoading label={t("library.preview.metaLoading")} />;
  }
  if (fileQuery.error) {
    if (isNotFoundError(fileQuery.error)) {
      return <MissingPreview fileId={fileId} onClose={onClose} />;
    }
    return (
      <ViewerErrorState
        error={fileQuery.error}
        title={t("library.preview.metaErrorTitle")}
        onRetry={() => void fileQuery.refetch()}
      />
    );
  }
  if (!file) {
    return (
      <p className="library-preview__chunk-empty-text">
        {translateApiError(fileQuery.error, t, "library.errors.generic")}
      </p>
    );
  }
  if (activeTab === "chunk") {
    return (
      <ChunkInspection
        file={file}
        requestedChunk={requestedChunk}
        effectiveChunk={effectiveChunk}
        onChunkChange={onChunkChange}
        chunkQuery={chunkQuery}
      />
    );
  }
  if (activeTab === "meta") {
    return <MetadataPanel file={file} />;
  }
  return <PagePreview file={file} isImage={classifyFile(file) === "image"} />;
}

function PreviewActions({
  file,
  onEdit,
  onMove,
  onCopy,
  onRename,
  onDelete,
}: {
  readonly file: FileSchema;
  readonly onEdit: () => void;
  readonly onMove: (target: FileOperationTarget) => void;
  readonly onCopy: (target: FileOperationTarget) => void;
  readonly onRename: (target: FileOperationTarget) => void;
  readonly onDelete: (target: FileOperationTarget) => void;
}) {
  const { t, formatNumber } = useI18n();
  const state = fileState(file);
  const markdown = classifyFile(file) === "markdown";
  return (
    <div className="library-preview__actions">
      <div className="library-preview__badges">
        <Badge tone={state.tone} dot>
          {t(state.labelKey)}
        </Badge>
        <Badge tone="neutral">v{file.version}</Badge>
        <Badge tone="neutral">{formatBytes(file.size_bytes)}</Badge>
        <Badge tone="neutral">
          {t(
            file.total_chunks === 1
              ? "library.units.chunkOne"
              : "library.units.chunkOther",
            { count: formatNumber(file.total_chunks) },
          )}
        </Badge>
      </div>
      <div className="library-preview__action-buttons">
        {markdown && file.is_current && !file.deleted_at ? (
          <Button variant="ghost" size="sm" onClick={onEdit}>
            <Icon name="pencil" size={14} />
            {t("library.editor.editFile")}
          </Button>
        ) : null}
        {file.has_original ? (
          <a
            className="btn btn--secondary btn--sm"
            href={fileDownloadUrl(file.id)}
            download={file.file_name}
          >
            <Icon name="arrow-down" size={14} />
            {t("library.common.download")}
          </a>
        ) : (
          <span className="library-preview__text-only">
            {t("library.preview.indexedTextOnly")}
          </span>
        )}
        {file.deleted_at ? null : (
          <>
            <Button variant="ghost" size="sm" onClick={() => onRename(operationTarget(file))}>
              <Icon name="pencil" size={14} />
              {t("library.common.rename")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onMove(operationTarget(file))}>
              <Icon name="branch" size={14} />
              {t("library.common.move")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onCopy(operationTarget(file))}>
              <Icon name="copy" size={14} />
              {t("library.common.copy")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="library-preview__delete"
              onClick={() => onDelete(operationTarget(file))}
            >
              <Icon name="trash" size={14} />
              {t("library.common.delete")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * The in-situ file preview: a 90vw desktop dialog that becomes full screen on
 * mobile. It keeps the shelf behind it, reuses `FileRenderer` for PDF/DOCX/
 * image/text/Markdown/CSV/JSON, and reads chunk windows from the file API.
 */
export function FilePreviewModal({
  fileId,
  requestedChunk,
  startInEdit = false,
  onClose,
  onChunkChange,
  onFileVersionChange,
  onEditModeChange,
  onMove,
  onCopy,
  onRename,
  onDelete,
}: FilePreviewModalProps) {
  const { t } = useI18n();
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<MarkdownEditorHandle>(null);
  const onCloseRef = useRef(onClose);
  const startInEditAppliedRef = useRef(false);
  const [activeTab, setActiveTab] = useState<PreviewTab>(
    requestedChunk > 1 ? "chunk" : "page",
  );
  const [editing, setEditing] = useState(false);

  useScrollLock(true);

  const fileQuery = useGetFile(fileId, { query: { retry: false } });
  const file = fileQuery.data;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // 切換檔案 id 會展開新的預覽工作階段；新的 `mode=edit` 連結由下方
  // effect 在中繼資料載入後套用。
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    startInEditAppliedRef.current = false;
    setEditing(false);
  }, [fileId]);

  // 深層連結可能在檔案查詢完成前就要求進入編輯模式。
  useEffect(() => {
    if (!startInEdit || startInEditAppliedRef.current || !file) {
      return;
    }
    startInEditAppliedRef.current = true;
    if (
      classifyFile(file) === "markdown" &&
      file.is_current &&
      !file.deleted_at
    ) {
      setEditing(true);
    } else {
      // URL 指向不能編輯的檔案時，清掉無效的 `mode=edit`。
      onEditModeChange?.(false);
    }
  }, [file, onEditModeChange, startInEdit]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Markdown 編輯器開啟時，Escape、Tab 與 Ctrl/Cmd+S 都由它接管。
      if (editing) {
        return;
      }
      // A move/delete dialog can sit above the preview. It owns Escape and Tab
      // while open, so the preview must not close underneath it.
      if (document.querySelector(".library-dialog-layer")) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.offsetParent !== null,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [editing]);

  const effectiveChunk = file
    ? clampChunk(requestedChunk, file.total_chunks || requestedChunk)
    : Math.max(1, requestedChunk);
  const chunkQuery = useReadFile(
    fileId,
    effectiveChunk,
    { chunk_range: 0 },
    {
      query: {
        enabled: activeTab === "chunk" && file !== undefined && file.total_chunks > 0,
        retry: false,
      },
    },
  );
  const kind = file ? classifyFile(file) : null;

  const handleCancelEdit = useCallback(() => {
    setEditing(false);
    onEditModeChange?.(false);
  }, [onEditModeChange]);

  const handleSaved = useCallback(
    (updatedFile: FileSchema) => {
      // 兩個 callback 可能在同一輪事件中各自更新 query string。先清掉
      // `mode`，再讓 `onFileVersionChange` 同時帶入新 file id 與 mode=null，
      // 確保最後一次導覽不會退回舊版本。
      onEditModeChange?.(false);
      onFileVersionChange(updatedFile.id);
      setEditing(false);
      setActiveTab("page");
    },
    [onEditModeChange, onFileVersionChange],
  );

  const handleStartEdit = useCallback(() => {
    setEditing(true);
    onEditModeChange?.(true);
  }, [onEditModeChange]);

  return (
    <div
      className={
        editing
          ? "modal library-preview library-preview--editing"
          : "modal library-preview"
      }
      onMouseDown={(event) => {
        if (!editing && event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        className="modal-dialog library-preview__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={editing ? undefined : titleId}
        aria-label={editing ? t("library.editor.editing") : undefined}
        tabIndex={-1}
      >
        {editing ? null : (
          <header className="modal-head library-preview__head">
            <div className="library-preview__identity">
              <p className="eyebrow">
                {kind
                  ? t("library.preview.eyebrowKind", { kind: kindLabel(kind, t) })
                  : t("library.preview.eyebrow")}
              </p>
              <h2 id={titleId} className="library-preview__title">
                {file?.file_name ?? t("library.preview.fileIdFallback", { id: fileId })}
              </h2>
              {file ? (
                <code className="library-preview__path">{file.raw_file_path}</code>
              ) : null}
            </div>

            <div
              className="tabs library-preview__tabs"
              role="tablist"
              aria-label={t("library.preview.sectionsAria")}
            >
              {PREVIEW_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  className={activeTab === tab.id ? "tab is-active" : "tab"}
                  onClick={() => setActiveTab(tab.id)}
                  disabled={!file}
                >
                  {t(tab.labelKey)}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="modal-btn-close"
              onClick={onClose}
              aria-label={t("library.common.closePreview")}
              title={t("library.common.closePreview")}
            >
              <Icon name="close" size={18} />
            </button>
          </header>
        )}

        {file && !editing ? (
          <PreviewActions
            file={file}
            onEdit={handleStartEdit}
            onMove={onMove}
            onCopy={onCopy}
            onRename={onRename}
            onDelete={onDelete}
          />
        ) : null}

        <div
          className={
            editing
              ? "modal-body library-preview__body library-preview__body--editing"
              : "modal-body library-preview__body"
          }
        >
          {editing && file ? (
            <MarkdownEditor
              ref={editorRef}
              mode="edit"
              file={file}
              onCancel={handleCancelEdit}
              onSaved={handleSaved}
            />
          ) : (
            <PreviewBody
              fileId={fileId}
              fileQuery={fileQuery}
              file={file}
              activeTab={activeTab}
              requestedChunk={requestedChunk}
              effectiveChunk={effectiveChunk}
              chunkQuery={chunkQuery}
              onChunkChange={onChunkChange}
              onClose={onClose}
            />
          )}
        </div>
      </div>
    </div>
  );
}
