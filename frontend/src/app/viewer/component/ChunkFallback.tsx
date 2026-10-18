import { useState } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { ViewerLoading, ViewerErrorState } from "./ViewerStates";
import { useChunkedText } from "./useChunkedText";

interface ChunkFallbackProps {
  readonly fileId: number;
  readonly totalChunks: number;
  readonly reason: string;
}

/**
 * Render the indexed text when the original bytes are absent or a document
 * renderer fails. This is a deliberate downgrade, never a silent one.
 */
export function ChunkFallback({ fileId, totalChunks, reason }: ChunkFallbackProps) {
  const [wrap, setWrap] = useState(true);
  const query = useChunkedText(fileId, totalChunks, totalChunks > 0);

  if (totalChunks === 0) {
    return (
      <ViewerErrorState
        error={new Error(reason)}
        title="No readable representation is available"
      />
    );
  }

  if (query.isLoading) {
    return <ViewerLoading label="Reassembling the indexed chunks" />;
  }

  if (query.error) {
    return (
      <ViewerErrorState
        error={query.error}
        title="The indexed text could not be read"
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (!query.data) {
    return null;
  }

  return (
    <div className="viewer-fallback">
      <div className="viewer-notice" role="note">
        <Icon name="info" size={16} />
        <p>
          {reason} The text below was reconstructed from {query.data.chunkCount} indexed
          chunk{query.data.chunkCount === 1 ? "" : "s"}; overlapping window boundaries can
          add a line break.
        </p>
        <Button variant="ghost" size="sm" onClick={() => setWrap((current) => !current)}>
          {wrap ? "No wrap" : "Wrap"}
        </Button>
      </div>
      <pre className={wrap ? "viewer-pre is-wrapped" : "viewer-pre"}>{query.data.text}</pre>
    </div>
  );
}
