import {
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
import { formatBytes, formatDateTime, formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { FileRenderer } from "../../viewer/component/FileViewer";
import { ViewerErrorState, ViewerLoading } from "../../viewer/component/ViewerStates";
import {
  classifyFile,
  fileDownloadUrl,
  kindLabel,
} from "../../viewer/component/viewer-utils";
import {
  clampChunk,
  describeError,
  isNotFoundError,
  type FileOperationTarget,
} from "./library-utils";

type PreviewTab = "page" | "chunk" | "meta";

interface FilePreviewModalProps {
  readonly fileId: number;
  readonly requestedChunk: number;
  readonly onClose: () => void;
  readonly onChunkChange: (chunk: number) => void;
  readonly onMove: (target: FileOperationTarget) => void;
  readonly onCopy: (target: FileOperationTarget) => void;
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

const PREVIEW_TABS: readonly { readonly id: PreviewTab; readonly label: string }[] = [
  { id: "page", label: "Page Preview" },
  { id: "chunk", label: "Chunk Inspection" },
  { id: "meta", label: "Metadata" },
];

function fileState(file: FileSchema): {
  readonly label: string;
  readonly tone: "moss" | "ochre" | "vermilion";
} {
  if (file.deleted_at) {
    return { label: "Deleted", tone: "vermilion" };
  }
  if (!file.is_current) {
    return { label: "History", tone: "ochre" };
  }
  return { label: "Current", tone: "moss" };
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
  return (
    <div className="library-preview__status">
      <span className="library-preview__status-mark" aria-hidden="true">
        <Icon name="info" size={22} />
      </span>
      <p className="eyebrow">File not found</p>
      <h3>This file is not on the shelf.</h3>
      <p>
        File #{fileId} may have been deleted, superseded, or never existed. The archive keeps
        history, but this preview link does not resolve.
      </p>
      <Button variant="secondary" size="sm" onClick={onClose}>
        Close preview
      </Button>
    </div>
  );
}

function FileStateNotice({ file }: { readonly file: FileSchema }) {
  if (!file.deleted_at && file.is_current) {
    return null;
  }
  return (
    <div className="viewer-notice viewer-notice--history" role="note">
      <Icon name="history" size={16} />
      <p>
        {file.deleted_at
          ? "This file is soft-deleted. It stays readable here and in history, but is absent from current paths and search."
          : "This edition is superseded. It remains addressable for history and citations, but is absent from current listings."}
      </p>
    </div>
  );
}

function ChunkResults({
  chunkQuery,
}: {
  readonly chunkQuery: UseQueryResult<FileChunksSchema, HTTPValidationError>;
}) {
  if (chunkQuery.isLoading) {
    return <ViewerLoading label="Reading the chunk window" />;
  }
  if (chunkQuery.error) {
    return (
      <ViewerErrorState
        error={chunkQuery.error}
        title="The chunk window could not be read"
        onRetry={() => void chunkQuery.refetch()}
      />
    );
  }
  if (!chunkQuery.data || chunkQuery.data.chunks.length === 0) {
    return <p className="library-preview__chunk-empty-text">This chunk is empty.</p>;
  }
  return (
    <div className="library-preview__chunk-list">
      {chunkQuery.data.chunks.map((chunk) => (
        <article className="library-preview__chunk" key={chunk.chunk}>
          <header className="library-preview__chunk-head">
            <span className="library-preview__chunk-index">#{chunk.chunk}</span>
            <span className="library-preview__chunk-meta">
              {formatNumber(chunk.char_count)} chars · {formatNumber(chunk.token_count)}{" "}
              tokens
            </span>
            {chunk.is_current ? null : <Badge tone="ochre">History</Badge>}
            <CopyButton
              value={chunk.content}
              label="Copy chunk"
              iconOnly
              title={`Copy chunk #${chunk.chunk}`}
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
  if (file.total_chunks === 0) {
    return (
      <div className="library-preview__chunk-empty">
        <Icon name="layers" size={22} />
        <h3>This file has no indexed chunks.</h3>
        <p>Only the original file is available. Open the Metadata tab for its stored fields.</p>
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
            Previous
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
            Next
            <Icon name="arrow-right" size={14} />
          </Button>
        </div>
        <span className="library-preview__chunk-hint">1-based chunk index</span>
      </div>

      {requestedChunk !== effectiveChunk ? (
        <p className="library-preview__clamp" role="status">
          Requested chunk {requestedChunk} is outside 1–{formatNumber(file.total_chunks)}.
          Showing chunk {effectiveChunk} instead.
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
  return (
    <div className="library-preview__stage">
      <FileStateNotice file={file} />
      <FileRenderer file={file} />
      {isImage && (file.ai_summary || file.ai_tags.length > 0) ? (
        <div className="library-preview__caption">
          {file.ai_summary ? (
            <div>
              <p className="eyebrow">Summary</p>
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
  return (
    <div className="library-preview__metadata">
      <dl className="meta-grid library-preview__meta">
        <MetaItem label="File name" value={file.file_name} />
        <MetaItem label="File ID" value={`#${file.id}`} />
        <MetaItem label="Path" value={file.raw_file_path} wide />
        <MetaItem label="MIME type" value={file.mime_type || "—"} />
        <MetaItem
          label="Extension"
          value={file.extension ? file.extension.toUpperCase() : "—"}
        />
        <MetaItem label="Document type" value={file.document_type || "—"} />
        <MetaItem label="Version" value={`v${file.version}`} />
        <MetaItem label="Current" value={file.is_current ? "Yes" : "No"} />
        <MetaItem label="Size" value={formatBytes(file.size_bytes)} />
        <MetaItem label="Indexed chunks" value={formatNumber(file.total_chunks)} />
        <MetaItem label="Original stored" value={file.has_original ? "Yes" : "No"} />
        <MetaItem
          label="Supersedes"
          value={file.supersedes_file_id !== null ? `File #${file.supersedes_file_id}` : "—"}
        />
        <MetaItem label="Created" value={formatDateTime(file.created_at)} />
        <MetaItem label="Updated" value={formatDateTime(file.updated_at)} />
        {file.deleted_at ? (
          <MetaItem label="Deleted" value={formatDateTime(file.deleted_at)} />
        ) : null}
        {file.ai_summary ? (
          <MetaItem
            label="Summary"
            value={<span className="library-preview__meta-text">{file.ai_summary}</span>}
            wide
          />
        ) : null}
        {file.ai_tags.length > 0 ? (
          <MetaItem
            label="Tags"
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
        Metadata comes from the file record. No checksum, job identifier, or page number is
        stored on `FileSchema`.
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
  if (fileQuery.isLoading) {
    return <ViewerLoading label="Reading the file metadata" />;
  }
  if (fileQuery.error) {
    if (isNotFoundError(fileQuery.error)) {
      return <MissingPreview fileId={fileId} onClose={onClose} />;
    }
    return (
      <ViewerErrorState
        error={fileQuery.error}
        title="The file metadata could not be read"
        onRetry={() => void fileQuery.refetch()}
      />
    );
  }
  if (!file) {
    return (
      <p className="library-preview__chunk-empty-text">
        {describeError(fileQuery.error)}
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
  onMove,
  onCopy,
  onDelete,
}: {
  readonly file: FileSchema;
  readonly onMove: (target: FileOperationTarget) => void;
  readonly onCopy: (target: FileOperationTarget) => void;
  readonly onDelete: (target: FileOperationTarget) => void;
}) {
  const state = fileState(file);
  return (
    <div className="library-preview__actions">
      <div className="library-preview__badges">
        <Badge tone={state.tone} dot>
          {state.label}
        </Badge>
        <Badge tone="neutral">v{file.version}</Badge>
        <Badge tone="neutral">{formatBytes(file.size_bytes)}</Badge>
        <Badge tone="neutral">{formatNumber(file.total_chunks)} chunks</Badge>
      </div>
      <div className="library-preview__action-buttons">
        {file.has_original ? (
          <a
            className="btn btn--secondary btn--sm"
            href={fileDownloadUrl(file.id)}
            download={file.file_name}
          >
            <Icon name="arrow-down" size={14} />
            Download
          </a>
        ) : (
          <span className="library-preview__text-only">Indexed text only</span>
        )}
        {file.deleted_at ? null : (
          <>
            <Button variant="ghost" size="sm" onClick={() => onMove(operationTarget(file))}>
              <Icon name="branch" size={14} />
              Move
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onCopy(operationTarget(file))}>
              <Icon name="copy" size={14} />
              Copy
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="library-preview__delete"
              onClick={() => onDelete(operationTarget(file))}
            >
              <Icon name="trash" size={14} />
              Delete
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
  onClose,
  onChunkChange,
  onMove,
  onCopy,
  onDelete,
}: FilePreviewModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const [activeTab, setActiveTab] = useState<PreviewTab>(
    requestedChunk > 1 ? "chunk" : "page",
  );

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
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
  }, []);

  const fileQuery = useGetFile(fileId, { query: { retry: false } });
  const file = fileQuery.data;
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

  return (
    <div
      className="modal library-preview"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        className="modal-dialog library-preview__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal-head library-preview__head">
          <div className="library-preview__identity">
            <p className="eyebrow">File preview{kind ? ` · ${kindLabel(kind)}` : ""}</p>
            <h2 id={titleId} className="library-preview__title">
              {file?.file_name ?? `File #${fileId}`}
            </h2>
            {file ? <code className="library-preview__path">{file.raw_file_path}</code> : null}
          </div>

          <div
            className="tabs library-preview__tabs"
            role="tablist"
            aria-label="Preview sections"
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
                {tab.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            className="modal-btn-close"
            onClick={onClose}
            aria-label="Close preview"
            title="Close preview"
          >
            <Icon name="close" size={18} />
          </button>
        </header>

        {file ? (
          <PreviewActions
            file={file}
            onMove={onMove}
            onCopy={onCopy}
            onDelete={onDelete}
          />
        ) : null}

        <div className="modal-body library-preview__body">
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
        </div>
      </div>
    </div>
  );
}
