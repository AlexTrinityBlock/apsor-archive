import { lazy, Suspense, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useGetFile } from "../../generated-apis-types/files/files";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { formatBytes, formatDateTime, formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { CitedChunk } from "./CitedChunk";
import { TextSheet } from "./TextSheet";
import { ViewerErrorState, ViewerLoading, ViewerMissing } from "./ViewerStates";
import { ViewerShell } from "./ViewerShell";
import {
  classifyFile,
  fileContentUrl,
  fileDownloadUrl,
  kindLabel,
  parseViewerId,
  viewerErrorStatus,
  type ViewerKind,
} from "./viewer-utils";

const PdfView = lazy(() =>
  import("./PdfView").then((module) => ({ default: module.PdfView })),
);
const DocxView = lazy(() =>
  import("./DocxView").then((module) => ({ default: module.DocxView })),
);
const ImageView = lazy(() =>
  import("./ImageView").then((module) => ({ default: module.ImageView })),
);

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

function UnsupportedViewer({ file }: { readonly file: FileSchema }) {
  return (
    <section className="viewer-unsupported">
      <span className="viewer-unsupported__mark" aria-hidden="true">
        <Icon name="file" size={30} />
      </span>
      <p className="eyebrow">No inline renderer</p>
      <h2>This original is safe to download, but not to render here.</h2>
      <p>
        The stored type is <code>{file.mime_type}</code>. The viewer deliberately renders
        only PDF, DOCX, images, and text-like formats; other binaries never execute in the
        archive.
      </p>
      <dl className="viewer-unsupported__meta">
        <div>
          <dt>File name</dt>
          <dd>{file.file_name}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{formatBytes(file.size_bytes)}</dd>
        </div>
        <div>
          <dt>Indexed chunks</dt>
          <dd>{formatNumber(file.total_chunks)}</dd>
        </div>
      </dl>
      <div className="viewer-unsupported__actions">
        <a
          className="btn btn--secondary btn--sm"
          href={fileDownloadUrl(file.id)}
          download={file.file_name}
        >
          <Icon name="arrow-down" size={15} />
          Download original
        </a>
        <a
          className="btn btn--ghost btn--sm"
          href={fileContentUrl(file.id)}
          target="_blank"
          rel="noopener noreferrer"
        >
          <Icon name="external" size={15} />
          Open raw content
        </a>
      </div>
    </section>
  );
}

function rendererFor(file: FileSchema): ReactNode {
  const kind: ViewerKind = classifyFile(file);
  const contentUrl = fileContentUrl(file.id);
  switch (kind) {
    case "pdf":
      return (
        <PdfView
          fileId={file.id}
          fileUrl={contentUrl}
          fileName={file.file_name}
          downloadUrl={fileDownloadUrl(file.id)}
        />
      );
    case "docx":
      return (
        <DocxView
          fileId={file.id}
          fileUrl={contentUrl}
          fileName={file.file_name}
          totalChunks={file.total_chunks}
        />
      );
    case "image":
      return (
        <ImageView
          src={contentUrl}
          alt={file.file_name}
          downloadUrl={fileDownloadUrl(file.id)}
          downloadName={file.file_name}
        />
      );
    case "markdown":
    case "json":
    case "csv":
    case "text":
      return <TextSheet file={file} />;
    default:
      return <UnsupportedViewer file={file} />;
  }
}

interface FileRendererProps {
  readonly file: FileSchema;
  readonly chunk?: number | null;
}

/**
 * The reusable body of a file viewer: cited chunk plus the actual renderer.
 *
 * Dock inspectors use this without the standalone `ViewerShell`; the viewer
 * page composes the same component so both surfaces read one implementation.
 */
export function FileRenderer({ file, chunk = null }: FileRendererProps) {
  return (
    <>
      {chunk !== null ? <CitedChunk fileId={file.id} chunk={chunk} /> : null}
      <Suspense fallback={<ViewerLoading label="Preparing the renderer" />}>
        {rendererFor(file)}
      </Suspense>
    </>
  );
}

/**
 * The standalone file viewer for `/viewer/file/:fileId`.
 *
 * Metadata comes from the generated `useGetFile` hook. Rendered originals stay
 * on same-origin, auth-protected URLs; PDF/DOCX/image engines load lazily so a
 * text leaf never downloads a PDF or DOCX bundle.
 */
export function FileViewer({ fileId }: { readonly fileId: number }) {
  const [searchParams] = useSearchParams();
  const chunk = parseViewerId(searchParams.get("chunk") ?? undefined);
  const fileQuery = useGetFile(fileId, { query: { retry: false } });
  const file = fileQuery.data;
  const kind = file ? classifyFile(file) : "unsupported";
  const state = file ? fileState(file) : null;
  const status = viewerErrorStatus(fileQuery.error);

  if (fileQuery.isLoading) {
    return (
      <ViewerShell
        kind="File leaf"
        title={`Reading file #${fileId}`}
        backTo="/library"
        backLabel="File library"
      >
        <ViewerLoading label="Reading the leaf metadata" />
      </ViewerShell>
    );
  }

  if (fileQuery.error || !file) {
    const missing = status === 404;
    return (
      <ViewerShell
        kind="File leaf"
        title={`File #${fileId}`}
        backTo="/library"
        backLabel="File library"
      >
        {missing ? (
          <ViewerMissing
            title="This file is not on the shelf."
            message={`File #${fileId} may have been removed, superseded, or never existed. The archive keeps history, but this link does not resolve.`}
            backTo="/library"
            backLabel="Back to the file library"
          />
        ) : (
          <ViewerErrorState
            error={fileQuery.error}
            title="The file metadata could not be read"
            onRetry={() => void fileQuery.refetch()}
          />
        )}
      </ViewerShell>
    );
  }

  return (
    <ViewerShell
      kind={`File leaf · ${kindLabel(kind)}`}
      title={file.file_name}
      path={file.raw_file_path}
      backTo="/library"
      backLabel="File library"
      actions={
        file.has_original ? (
          <>
            <a
              className="btn btn--ghost btn--sm"
              href={fileContentUrl(file.id)}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Icon name="external" size={15} />
              <span>Open original</span>
            </a>
            <a
              className="btn btn--secondary btn--sm"
              href={fileDownloadUrl(file.id)}
              download={file.file_name}
            >
              <Icon name="arrow-down" size={15} />
              <span>Download</span>
            </a>
          </>
        ) : (
          <span className="viewer-chip">Text-only record</span>
        )
      }
      meta={
        <>
          {state ? (
            <Badge tone={state.tone} dot>
              {state.label}
            </Badge>
          ) : null}
          <Badge tone="neutral">v{file.version}</Badge>
          <Badge tone="neutral">{formatBytes(file.size_bytes)}</Badge>
          <Badge tone="neutral">{formatNumber(file.total_chunks)} chunks</Badge>
          <span className="viewer-heading__date">
            <Icon name="clock" size={13} />
            <time dateTime={file.updated_at}>{formatDateTime(file.updated_at)}</time>
          </span>
        </>
      }
    >
      {file.deleted_at || !file.is_current ? (
        <div className="viewer-notice viewer-notice--history" role="note">
          <Icon name="history" size={16} />
          <p>
            {file.deleted_at
              ? "This leaf is soft-deleted. It stays readable here and in history, but is absent from current paths and search."
              : "This edition is superseded. It remains addressable for history and citations, but is absent from current listings."}
          </p>
        </div>
      ) : null}

      <FileRenderer file={file} chunk={chunk} />
    </ViewerShell>
  );
}
