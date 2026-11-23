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
import { thumbCacheKey, thumbKindFor } from "./thumb-kind";
import { useInView } from "./useInView";

const DocxThumb = lazy(() =>
  import("./DocxThumb").then((module) => ({ default: module.DocxThumb })),
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
 * Images use the stored original through the browser cache. PDF and PPTX
 * first pages are rendered lazily into the session cache. DOCX renders a real
 * first page inside a sandboxed iframe on cards only; a 32px list row gets a
 * paper tile instead because the parse is expensive and the result unreadable.
 */
export function FileThumb({ file, variant }: FileThumbProps) {
  // A replacement version keeps the file id but changes the cache key, so the
  // inner component remounts instead of keeping the old data URL or failure
  // marker. This also resets per-version image and frame error state.
  return (
    <FileThumbContent key={thumbCacheKey(file)} file={file} variant={variant} />
  );
}

function FileThumbContent({ file, variant }: FileThumbProps) {
  const kind = thumbKindFor(file.raw_file_path);
  const key = thumbCacheKey(file);
  const [entry, setEntry] = useState<ThumbEntry | undefined>(() => getThumb(key));
  const [imageBroken, setImageBroken] = useState(false);
  const [docxBroken, setDocxBroken] = useState(false);
  const [hostRef, inView] = useInView<HTMLSpanElement>();

  useEffect(() => {
    if (!inView || entry !== undefined || !file.has_original) {
      return;
    }
    if (kind !== "pdf" && kind !== "pptx") {
      return;
    }
    const controller = new AbortController();
    let disposed = false;

    const run = async (signal: AbortSignal): Promise<string> => {
      if (kind === "pdf") {
        const { renderPdfThumb } = await import("./render-pdf-thumb");
        return renderPdfThumb(file.file_id, signal);
      }
      const { renderPptxThumb } = await import("./render-pptx-thumb");
      return renderPptxThumb(file.file_id, signal);
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
  }, [entry, file.file_id, file.has_original, inView, key, kind]);

  let content: ReactNode;
  if (!file.has_original) {
    content = <TypeTile variant={variant} />;
  } else if (kind === "docx") {
    if (variant === "row") {
      content = <TypeTile variant="row" />;
    } else if (docxBroken) {
      content = <TypeTile variant="card" />;
    } else if (inView) {
      content = (
        <Suspense fallback={<PaperSkeleton />}>
          <DocxThumb
            fileId={file.file_id}
            fileName={file.file_name}
            onFailure={() => setDocxBroken(true)}
          />
        </Suspense>
      );
    } else {
      content = <PaperSkeleton />;
    }
  } else if (kind === "image") {
    content = imageBroken ? (
      <TypeTile variant={variant} />
    ) : (
      <img
        className="library-thumb__image"
        src={getGetFileContentUrl(file.file_id)}
        alt=""
        loading="lazy"
        decoding="async"
        draggable={false}
        onError={() => setImageBroken(true)}
      />
    );
  } else if (kind === "pdf" || kind === "pptx") {
    if (entry?.kind === "image") {
      content = (
        <img
          className="library-thumb__document"
          src={entry.dataUrl}
          alt=""
          draggable={false}
          onError={() => {
            setThumbFailed(key);
            setEntry({ kind: "failed" });
          }}
        />
      );
    } else if (entry?.kind === "failed") {
      content = <TypeTile variant={variant} />;
    } else {
      content = <PaperSkeleton />;
    }
  } else {
    content = <TypeTile variant={variant} />;
  }

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
