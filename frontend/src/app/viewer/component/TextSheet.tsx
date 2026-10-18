import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { CsvSheet } from "./CsvSheet";
import { ViewerErrorState, ViewerLoading } from "./ViewerStates";
import { useChunkedText } from "./useChunkedText";
import {
  classifyFile,
  countLines,
  fetchViewerText,
  fileContentUrl,
  fileDownloadUrl,
  kindLabel,
  prettyJson,
  textMode,
  ViewerResourceError,
} from "./viewer-utils";
const MarkdownSheet = lazy(() =>
  import("./MarkdownSheet").then((module) => ({ default: module.MarkdownSheet })),
);

interface TextSheetProps {
  readonly file: FileSchema;
}

interface TextToolbarProps {
  readonly file: FileSchema;
  readonly kind: ReturnType<typeof classifyFile>;
  readonly content: string;
  readonly lineCount: number;
  readonly wrap: boolean;
  readonly copied: boolean;
  readonly usingChunks: boolean;
  readonly onToggleWrap: () => void;
  readonly onCopy: () => void;
}

function TextToolbar({
  file,
  kind,
  content,
  lineCount,
  wrap,
  copied,
  usingChunks,
  onToggleWrap,
  onCopy,
}: TextToolbarProps) {
  return (
    <div className="viewer-toolbar">
      <div className="viewer-toolbar__stats">
        <span className="viewer-toolbar__kind">{kindLabel(kind)}</span>
        <span>{formatNumber(content.length)} chars</span>
        <span aria-hidden="true">·</span>
        <span>{formatNumber(lineCount)} lines</span>
        {usingChunks ? <span className="viewer-chip">Indexed chunks</span> : null}
      </div>
      <div className="viewer-toolbar__actions">
        <Button variant="ghost" size="sm" onClick={onToggleWrap} aria-pressed={wrap}>
          {wrap ? "No wrap" : "Wrap"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onCopy}
          disabled={content.length === 0}
        >
          <Icon name={copied ? "check" : "copy"} size={15} />
          <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
        </Button>
        {usingChunks ? null : (
          <a
            className="btn btn--ghost btn--sm"
            href={fileDownloadUrl(file.id)}
            download={file.file_name}
          >
            <Icon name="arrow-down" size={15} />
            Download
          </a>
        )}
      </div>
    </div>
  );
}

function JsonSheet({ content, wrap }: { readonly content: string; readonly wrap: boolean }) {
  const json = useMemo(() => prettyJson(content), [content]);
  return (
    <div className="viewer-sheet">
      {json.valid ? null : (
        <div className="viewer-notice" role="note">
          <Icon name="info" size={16} />
          <p>This file is labelled JSON but is not valid JSON; showing the raw text.</p>
        </div>
      )}
      <pre className={wrap ? "viewer-pre is-wrapped" : "viewer-pre"}>{json.formatted}</pre>
    </div>
  );
}

interface TextBodyProps {
  readonly mode: "markdown" | "json" | "csv" | "text";
  readonly content: string;
  readonly wrap: boolean;
}

function TextBody({ mode, content, wrap }: TextBodyProps) {
  if (mode === "markdown") {
    return (
      <div className="viewer-sheet">
        <Suspense fallback={<ViewerLoading label="Typesetting the Markdown" />}>
          <MarkdownSheet content={content} />
        </Suspense>
      </div>
    );
  }
  if (mode === "csv") {
    return (
      <div className="viewer-sheet viewer-sheet--table">
        <CsvSheet content={content} wrap={wrap} />
      </div>
    );
  }
  if (mode === "json") {
    return <JsonSheet content={content} wrap={wrap} />;
  }
  return (
    <div className="viewer-sheet">
      <pre className={wrap ? "viewer-pre is-wrapped" : "viewer-pre"}>{content}</pre>
    </div>
  );
}

function SourceNotice({ chunkCount }: { readonly chunkCount: number }) {
  return (
    <div className="viewer-notice" role="note">
      <Icon name="info" size={16} />
      <p>
        The original bytes are not stored for this record. The sheet was rebuilt from{" "}
        {formatNumber(chunkCount)} indexed chunks; overlaps can add a line break at window
        boundaries.
      </p>
    </div>
  );
}

function isUnavailable(error: unknown): boolean {
  return error instanceof ViewerResourceError && error.status === 404;
}

/**
 * The reading sheet for text, Markdown, JSON, and CSV originals.
 *
 * Text-only records without stored bytes fall back to the indexed chunks with
 * a visible notice. Markdown is rendered with raw HTML skipped and remote
 * images suppressed; JSON is pretty-printed, never evaluated.
 */
export function TextSheet({ file }: TextSheetProps) {
  const kind = classifyFile(file);
  const mode = textMode(kind);
  const [wrap, setWrap] = useState(mode !== "json" && mode !== "csv");
  const [copied, setCopied] = useState(false);

  const hasStoredOriginal = file.has_original;
  const contentQuery = useQuery({
    queryKey: ["viewer", "file-text", file.id],
    queryFn: ({ signal }) => fetchViewerText(fileContentUrl(file.id), signal),
    enabled: hasStoredOriginal,
    retry: false,
    staleTime: 5 * 60_000,
  });

  // Text-only records skip the original probe entirely. A 404 from a record
  // that claims to have an original still falls back to the indexed chunks.
  const unavailable = !hasStoredOriginal || isUnavailable(contentQuery.error);
  const chunksQuery = useChunkedText(file.id, file.total_chunks, unavailable);
  const usingChunks = unavailable && chunksQuery.data !== undefined;
  const originalText = hasStoredOriginal ? contentQuery.data : undefined;
  const chunkText = usingChunks ? chunksQuery.data?.text : undefined;
  const content = originalText ?? chunkText ?? "";
  const loading =
    (hasStoredOriginal && contentQuery.isLoading) ||
    (unavailable && chunksQuery.isLoading);
  const lineCount = countLines(content);

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(false), 2_000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  if (loading) {
    return <ViewerLoading label="Reading the stored text" />;
  }

  if (unavailable && chunksQuery.error) {
    return (
      <ViewerErrorState
        error={chunksQuery.error}
        title="Neither the original nor its indexed chunks could be read"
        onRetry={() => void chunksQuery.refetch()}
      />
    );
  }

  if (contentQuery.error && !unavailable) {
    return (
      <ViewerErrorState
        error={contentQuery.error}
        title="The stored original could not be read"
        onRetry={() => void contentQuery.refetch()}
        downloadUrl={fileDownloadUrl(file.id)}
        downloadName={file.file_name}
      />
    );
  }

  if (unavailable && file.total_chunks === 0) {
    return (
      <ViewerErrorState
        error={
          new ViewerResourceError(
            404,
            "file_content_unavailable",
            "This record was created as text and has no stored original or indexed chunks.",
          )
        }
        title="This leaf has no readable body"
      />
    );
  }

  return (
    <div className="viewer-text">
      <TextToolbar
        file={file}
        kind={kind}
        content={content}
        lineCount={lineCount}
        wrap={wrap}
        copied={copied}
        usingChunks={usingChunks}
        onToggleWrap={() => setWrap((current) => !current)}
        onCopy={() => void handleCopy()}
      />

      {usingChunks ? (
        <SourceNotice chunkCount={chunksQuery.data?.chunkCount ?? 0} />
      ) : null}

      <TextBody mode={mode} content={content} wrap={wrap} />
    </div>
  );
}
