import { lazy, Suspense, type ReactNode } from "react";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { formatBytes, formatNumber } from "../../../lib/format";
import { Icon } from "../../component/Icon";
import { CitedChunk } from "./CitedChunk";
import { TextSheet } from "./TextSheet";
import { ViewerLoading } from "./ViewerStates";
import {
  classifyFile,
  fileContentUrl,
  fileDownloadUrl,
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
 * The reusable body of a file preview: cited chunk plus the actual renderer.
 * Both the Library preview modal and the Chat inspector use this component, so
 * PDF/DOCX/image/text behavior has one implementation.
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
