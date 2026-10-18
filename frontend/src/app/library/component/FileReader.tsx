import { useState } from "react";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useGetFile, useReadFile } from "../../generated-apis-types/files/files";
import { formatBytes, formatDateTime, formatNumber } from "../../../lib/format";
import { highlightTerms } from "../../../lib/highlight";
import { Badge } from "../../component/Badge";
import { Button, buttonClassName } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { QueryState } from "../../component/QueryState";
import { DeleteFileDialog } from "./DeleteFileDialog";
import { LibraryBreadcrumbs } from "./LibraryBreadcrumbs";
import { clampChunk, isNotFoundError } from "./library-utils";

interface FileReaderProps {
  readonly fileId: number;
  readonly requestedChunk: number;
  readonly query: string;
  readonly backLabel: string;
  readonly onClose: () => void;
  readonly onChunkChange: (chunk: number) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onDeleted: () => void;
  readonly onClearQuery: () => void;
}

function fileState(file: FileSchema): { readonly label: string; readonly tone: "moss" | "ochre" | "vermilion" } {
  if (file.deleted_at) {
    return { label: "Deleted", tone: "vermilion" };
  }
  if (!file.is_current) {
    return { label: "History", tone: "ochre" };
  }
  return { label: "Current", tone: "moss" };
}

function fileNote(file: FileSchema): string {
  if (file.deleted_at) {
    return "This leaf has been soft-deleted. It no longer appears in paths or search, but history still resolves it.";
  }
  if (!file.is_current) {
    return "This edition is superseded. It remains addressable through history and stays out of current listings and search.";
  }
  return "This leaf is current. Soft delete removes it from the shelf and search while the version chain stays in history.";
}

function MissingFile({ fileId, onClose }: { readonly fileId: number; readonly onClose: () => void }) {
  return (
    <Panel tone="plain" className="library-not-found reveal reveal-2">
      <p className="eyebrow">Leaf not found</p>
      <h2>This file is not on the current shelf.</h2>
      <p>
        File #{fileId} may have been soft-deleted or superseded. The archive keeps old leaves in
        history, but this link points to an edition the shelf no longer serves.
      </p>
      <div className="library-not-found__actions">
        <Button variant="secondary" size="sm" onClick={onClose}>
          Back to the library
        </Button>
        <span className="library-not-found__hint">Try browsing the path again.</span>
      </div>
    </Panel>
  );
}

/**
 * A full-width reader for one file leaf: metadata, download, soft delete, and a
 * 1-based chunk window with neighbours. A path query highlights matching grains
 * in the text without rendering any HTML from the file.
 */
export function FileReader({
  fileId,
  requestedChunk,
  query,
  backLabel,
  onClose,
  onChunkChange,
  onOpenFolder,
  onDeleted,
  onClearQuery,
}: FileReaderProps) {
  const [deleteOpen, setDeleteOpen] = useState(false);

  const fileQuery = useGetFile(fileId, { query: { enabled: fileId > 0 } });
  const file = fileQuery.data;
  const totalChunks = file?.total_chunks ?? 0;
  const effectiveChunk = clampChunk(requestedChunk, totalChunks || requestedChunk);
  const chunksQuery = useReadFile(
    fileId,
    effectiveChunk,
    { chunk_range: 1 },
    { query: { enabled: file !== undefined && file.total_chunks > 0 } },
  );

  if (fileQuery.isLoading) {
    return (
      <QueryState loading error={null} loadingLabel="Reading the file leaf">
        {null}
      </QueryState>
    );
  }

  if (fileQuery.error) {
    if (isNotFoundError(fileQuery.error)) {
      return <MissingFile fileId={fileId} onClose={onClose} />;
    }
    return (
      <QueryState loading={false} error={fileQuery.error}>
        {null}
      </QueryState>
    );
  }

  if (!file) {
    return null;
  }

  const state = fileState(file);
  const chunkStart = chunksQuery.data?.chunk_start ?? effectiveChunk;
  const chunkEnd = chunksQuery.data?.chunk_end ?? effectiveChunk;
  const outOfRange = totalChunks > 0 && (requestedChunk > totalChunks || requestedChunk < 1);

  return (
    <div className="library-reader reveal reveal-2">
      <div className="library-reader__top">
        <Button variant="ghost" size="sm" className="library-reader__back" onClick={onClose}>
          <Icon name="arrow-right" size={15} className="library-back-icon" />
          {backLabel}
        </Button>
        <LibraryBreadcrumbs path={file.raw_file_path} leaf onNavigate={onOpenFolder} />
      </div>

      <Panel tone="moss" className="library-reader__sheet" corners>
        <div className="library-reader__identity">
          <div className="library-reader__heading">
            <p className="eyebrow">File leaf · {state.label.toLowerCase()}</p>
            <h2 className="library-reader__title">{file.file_name}</h2>
            <code className="library-reader__path">{file.raw_file_path}</code>
          </div>
          <div className="library-reader__status">
            <Badge tone={state.tone} dot>
              {state.label}
            </Badge>
            <Badge tone="neutral">v{file.version}</Badge>
            {file.supersedes_file_id !== null ? (
              <Badge tone="neutral">after #{file.supersedes_file_id}</Badge>
            ) : null}
          </div>
        </div>

        <dl className="library-reader__meta">
          <div>
            <dt>Version</dt>
            <dd>v{file.version}</dd>
          </div>
          <div>
            <dt>Chunks</dt>
            <dd>{formatNumber(file.total_chunks)}</dd>
          </div>
          <div>
            <dt>Size</dt>
            <dd>{formatBytes(file.size_bytes)}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>
              <time dateTime={file.updated_at}>{formatDateTime(file.updated_at)}</time>
            </dd>
          </div>
          <div>
            <dt>Created</dt>
            <dd>
              <time dateTime={file.created_at}>{formatDateTime(file.created_at)}</time>
            </dd>
          </div>
          <div>
            <dt>Type</dt>
            <dd>{file.extension ? file.extension.replace(/^\./, "").toUpperCase() : "TEXT"}</dd>
          </div>
        </dl>

        <div className="library-reader__actions">
          <a
            className={buttonClassName({ variant: "secondary", size: "sm" })}
            href={`/api/v1/files/${file.id}/download`}
            download={file.file_name}
          >
            <Icon name="arrow-down" size={15} />
            Download original
          </a>
          {file.deleted_at ? null : (
            <Button
              variant="ghost"
              size="sm"
              className="library-reader__delete"
              onClick={() => setDeleteOpen(true)}
            >
              <Icon name="history" size={15} />
              Soft delete
            </Button>
          )}
        </div>

        <p className="library-reader__note">{fileNote(file)}</p>
      </Panel>

      <QueryState
        loading={chunksQuery.isLoading}
        error={chunksQuery.error}
        loadingLabel="Reading the chunk window"
      >
        {chunksQuery.data ? (
          <Panel
            tone="paper"
            padded={false}
            className="library-reader__chunks"
            eyebrow="Reader"
            title={`Chunks ${chunkStart}–${chunkEnd} of ${formatNumber(chunksQuery.data.total_chunks)}`}
            action={
              <Badge tone={chunksQuery.isFetching ? "ochre" : "moss"}>
                {chunksQuery.isFetching ? "Reading…" : "1-based"}
              </Badge>
            }
          >
            <div className="library-reader__chunkbar">
              <div className="library-reader__chunknav">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onChunkChange(effectiveChunk - 1)}
                  disabled={effectiveChunk <= 1 || chunksQuery.isFetching}
                >
                  <Icon name="arrow-right" size={14} className="library-back-icon" />
                  Previous
                </Button>
                <span className="library-reader__chunk-position">#{effectiveChunk}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => onChunkChange(effectiveChunk + 1)}
                  disabled={effectiveChunk >= chunksQuery.data.total_chunks || chunksQuery.isFetching}
                >
                  Next
                  <Icon name="arrow-right" size={14} />
                </Button>
              </div>
              <div className="library-reader__chunkhint">
                {query ? (
                  <>
                    <span className="eyebrow">Highlighting</span>
                    <code>“{query}”</code>
                    <Button variant="ghost" size="sm" onClick={onClearQuery}>
                      Clear
                    </Button>
                  </>
                ) : (
                  <span>Each chunk keeps its 1-based index and character count.</span>
                )}
              </div>
            </div>

            {outOfRange ? (
              <p className="library-reader__clamp" role="status">
                Requested chunk {requestedChunk} is outside 1–{totalChunks}. Showing chunk{" "}
                {effectiveChunk} instead.
              </p>
            ) : null}

            {chunksQuery.data.chunks.length === 0 ? (
              <p className="library-reader__empty">This file has no readable chunks.</p>
            ) : (
              <div className="library-chunks">
                {chunksQuery.data.chunks.map((chunk) => (
                  <article className="library-chunk" id={`chunk-${chunk.chunk}`} key={chunk.chunk}>
                    <header className="library-chunk__head">
                      <span className="library-chunk__index">#{chunk.chunk}</span>
                      <span className="library-chunk__meta">
                        {formatNumber(chunk.char_count)} chars · {formatNumber(chunk.token_count)}{" "}
                        tokens
                      </span>
                      {chunk.is_current ? null : <Badge tone="ochre">History</Badge>}
                    </header>
                    <pre className="library-chunk__body">{highlightTerms(chunk.content, query)}</pre>
                  </article>
                ))}
              </div>
            )}
          </Panel>
        ) : null}
      </QueryState>

      {deleteOpen ? (
        <DeleteFileDialog
          file={file}
          onClose={() => setDeleteOpen(false)}
          onDeleted={onDeleted}
        />
      ) : null}
    </div>
  );
}
