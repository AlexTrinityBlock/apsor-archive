import { Link } from "react-router-dom";

import { useReadFile } from "../../generated-apis-types/files/files";
import { Icon } from "../../component/Icon";
import { formatNumber } from "../../../lib/format";

interface CitedChunkProps {
  readonly fileId: number;
  readonly chunk: number;
}

/** A compact cited-passage card for `?chunk=N` deep links from the agent. */
export function CitedChunk({ fileId, chunk }: CitedChunkProps) {
  const query = useReadFile(fileId, chunk, { chunk_range: 0 }, { query: { retry: false } });

  return (
    <aside className="viewer-citation" aria-label={`Cited chunk ${chunk}`}>
      <div className="viewer-citation__head">
        <span className="eyebrow">
          <Icon name="quote" size={13} /> Cited passage · chunk {chunk}
        </span>
        <Link to={`/library?tab=files&file=${fileId}`} className="viewer-citation__clear">
          Open in library
        </Link>
      </div>
      {query.isLoading ? (
        <p className="viewer-citation__note">Reading the cited window…</p>
      ) : null}
      {query.error ? (
        <p className="viewer-citation__note">
          Chunk {chunk} is outside this file&apos;s readable window.
        </p>
      ) : null}
      {query.data ? (
        <>
          <pre className="viewer-citation__text">
            {query.data.chunks[0]?.content ?? "The cited chunk is empty."}
          </pre>
          <p className="viewer-citation__meta">
            {formatNumber(query.data.chunks[0]?.char_count ?? 0)} chars · window{" "}
            {query.data.chunk_start}–{query.data.chunk_end} of {formatNumber(query.data.total_chunks)}
          </p>
        </>
      ) : null}
    </aside>
  );
}
