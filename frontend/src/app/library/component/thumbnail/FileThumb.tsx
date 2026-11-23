import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";

import type { PathFileSchema } from "../../../generated-apis-types/schemas";
import { getGetFileContentUrl } from "../../../generated-apis-types/files/files";
import { Icon } from "../../../component/Icon";
import { fileKindLabel } from "../library-utils";
import { schedule } from "./render-queue";
import {
  getThumb,
  setThumbFailed,
  setThumbImage,
  type ThumbEntry,
} from "./thumb-cache";
import { thumbCacheKey, thumbKindFor, type ThumbKind } from "./thumb-kind";
import { useInView } from "./useInView";

const DocxThumb = lazy(() =>
  import("./DocxThumb").then((module) => ({ default: module.DocxThumb })),
);

// The Markdown renderer is deliberately split from the library page chunk.
const MarkdownThumb = lazy(() =>
  import("./MarkdownThumb").then((module) => ({ default: module.MarkdownThumb })),
);

interface FileThumbProps {
  readonly file: PathFileSchema;
  readonly variant: "card" | "row";
}

function TypeTile({ variant }: { readonly variant: "card" | "row" }) {
  return (
    <span className="library-thumb__tile">
      <Icon name="file" size={variant === "card" ? 26 : 15} />
    </span>
  );
}

function PaperSkeleton() {
  return <span className="library-thumb__paper" />;
}

/**
 * A decorative preview for one library file.
 *
 * Images use the stored original through the browser cache. PDF, PPTX, and
 * XLSX first pages are rendered lazily into the session cache; XLSX parsing
 * happens in a worker. DOCX renders a real first page inside a sandboxed iframe
 * on cards only. Markdown renders a scaled page of real typography, also on
 * cards only; a 32px list row gets a paper tile instead because the result is
 * unreadable and the fetch would be wasted.
 */
export function FileThumb({ file, variant }: FileThumbProps) {
  // A replacement version keeps the file id but changes the cache key, so the
  // inner component remounts instead of keeping the old data URL or failure
  // marker. This also resets per-version image and frame error state.
  return (
    <FileThumbContent key={thumbCacheKey(file)} file={file} variant={variant} />
  );
}

interface ThumbContentProps {
  readonly file: PathFileSchema;
  readonly variant: "card" | "row";
  readonly kind: ThumbKind;
  readonly entry: ThumbEntry | undefined;
  readonly inView: boolean;
  readonly imageBroken: boolean;
  readonly docxBroken: boolean;
  readonly markdownBroken: boolean;
  readonly cacheKey: string;
  readonly onDocxFailure: () => void;
  readonly onMarkdownFailure: () => void;
  readonly onImageFailure: () => void;
  readonly onDocumentFailure: () => void;
}

function docxThumbContent(props: ThumbContentProps): ReactNode {
  if (props.variant === "row") {
    return <TypeTile variant="row" />;
  }
  if (props.docxBroken) {
    return <TypeTile variant="card" />;
  }
  if (!props.inView) {
    return <PaperSkeleton />;
  }
  return (
    <Suspense fallback={<PaperSkeleton />}>
      <DocxThumb
        fileId={props.file.file_id}
        fileName={props.file.file_name}
        onFailure={props.onDocxFailure}
      />
    </Suspense>
  );
}

function markdownThumbContent(props: ThumbContentProps): ReactNode {
  if (props.variant === "row") {
    return <span className="library-thumb__paper library-thumb__paper--static" />;
  }
  if (props.markdownBroken || props.entry?.kind === "failed") {
    return <TypeTile variant="card" />;
  }
  if (!props.inView) {
    return <PaperSkeleton />;
  }
  return (
    <Suspense fallback={<PaperSkeleton />}>
      <MarkdownThumb
        fileId={props.file.file_id}
        cacheKey={props.cacheKey}
        onFailure={props.onMarkdownFailure}
      />
    </Suspense>
  );
}

function imageThumbContent(props: ThumbContentProps): ReactNode {
  if (props.imageBroken) {
    return <TypeTile variant={props.variant} />;
  }
  return (
    <img
      className="library-thumb__image"
      src={getGetFileContentUrl(props.file.file_id)}
      alt=""
      loading="lazy"
      decoding="async"
      draggable={false}
      onError={props.onImageFailure}
    />
  );
}

function documentThumbContent(props: ThumbContentProps): ReactNode {
  if (props.entry?.kind === "image") {
    return (
      <img
        className={
          props.kind === "xlsx"
            ? "library-thumb__sheet"
            : "library-thumb__document"
        }
        src={props.entry.dataUrl}
        alt=""
        draggable={false}
        onError={props.onDocumentFailure}
      />
    );
  }
  if (props.entry?.kind === "failed") {
    return <TypeTile variant={props.variant} />;
  }
  if (props.kind === "xlsx" && props.variant === "row") {
    return <TypeTile variant="row" />;
  }
  return <PaperSkeleton />;
}

function thumbContent(props: ThumbContentProps): ReactNode {
  if (!props.file.has_original) {
    return <TypeTile variant={props.variant} />;
  }
  switch (props.kind) {
    case "docx":
      return docxThumbContent(props);
    case "markdown":
      return markdownThumbContent(props);
    case "image":
      return imageThumbContent(props);
    case "pdf":
    case "pptx":
    case "xlsx":
      return documentThumbContent(props);
    default:
      return <TypeTile variant={props.variant} />;
  }
}

function FileThumbContent({ file, variant }: FileThumbProps) {
  const kind = thumbKindFor(file.raw_file_path);
  const key = thumbCacheKey(file);
  const [entry, setEntry] = useState<ThumbEntry | undefined>(() => getThumb(key));
  const [imageBroken, setImageBroken] = useState(false);
  const [docxBroken, setDocxBroken] = useState(false);
  const [markdownBroken, setMarkdownBroken] = useState(false);
  const [hostRef, inView] = useInView<HTMLSpanElement>();

  useEffect(() => {
    if (!inView || entry !== undefined || !file.has_original) {
      return;
    }
    if (kind !== "pdf" && kind !== "pptx" && kind !== "xlsx") {
      return;
    }
    // A list row is too small to read a sheet and must never start a parse.
    if (kind === "xlsx" && variant !== "card") {
      return;
    }
    const controller = new AbortController();
    let disposed = false;

    const run = async (signal: AbortSignal): Promise<string> => {
      if (kind === "pdf") {
        const { renderPdfThumb } = await import("./render-pdf-thumb");
        return renderPdfThumb(file.file_id, signal);
      }
      if (kind === "pptx") {
        const { renderPptxThumb } = await import("./render-pptx-thumb");
        return renderPptxThumb(file.file_id, signal);
      }
      const { renderXlsxThumb } = await import("./render-xlsx-thumb");
      return renderXlsxThumb(file.file_id, signal);
    };

    schedule(run, controller.signal).then(
      (dataUrl) => {
        if (disposed) {
          return;
        }
        setThumbImage(key, dataUrl);
        setEntry({ kind: "image", dataUrl });
      },
      () => {
        if (disposed) {
          return;
        }
        setThumbFailed(key);
        setEntry({ kind: "failed" });
      },
    );

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [entry, file.file_id, file.has_original, inView, key, kind, variant]);

  const content = thumbContent({
    file,
    variant,
    kind,
    entry,
    inView,
    imageBroken,
    docxBroken,
    markdownBroken,
    cacheKey: key,
    onDocxFailure: () => setDocxBroken(true),
    onMarkdownFailure: () => {
      setMarkdownBroken(true);
      setThumbFailed(key);
      setEntry({ kind: "failed" });
    },
    onImageFailure: () => setImageBroken(true),
    onDocumentFailure: () => {
      setThumbFailed(key);
      setEntry({ kind: "failed" });
    },
  });

  return (
    <span
      ref={hostRef}
      className={variant === "card" ? "library-file-card__thumb" : "library-row__thumb library-row__icon--file"}
      aria-hidden="true"
    >
      {content}
      {variant === "card" ? (
        <span className="file-type-pill library-file-card__thumb-pill">
          {fileKindLabel(file.raw_file_path)}
        </span>
      ) : null}
    </span>
  );
}
