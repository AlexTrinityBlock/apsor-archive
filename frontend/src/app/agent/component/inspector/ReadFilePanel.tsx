import { formatNumber, truncate } from "../../../../lib/format";
import {
  numberField,
  recordId,
  recordList,
  textField,
} from "../../trace";
import {
  InspectorFileStage,
  LivePanel,
  PanelEmpty,
  PanelLink,
  type PanelProps,
} from "./common";

interface ChunkRecord {
  readonly index: number | null;
  readonly chars: number | null;
  readonly tokens: number | null;
  readonly excerpt: string;
}

function chunksOf(data: Record<string, unknown> | null): ChunkRecord[] {
  return recordList(data?.chunks).map((record) => {
    const excerpt = textField(record, "excerpt") ?? textField(record, "content") ?? "";
    return {
      index: numberField(record, "chunk"),
      chars: numberField(record, "char_count"),
      tokens: numberField(record, "token_count"),
      excerpt: excerpt.length > 520 ? `${truncate(excerpt, 520)}` : excerpt,
    };
  });
}

function ChunkWindow({ chunks }: { readonly chunks: readonly ChunkRecord[] }) {
  if (chunks.length === 0) {
    return (
      <p className="pi-manuscript__quiet">
        This result recorded chunk metadata only. The embedded file below is
        the authoritative text.
      </p>
    );
  }
  return (
    <ol className="pi-manuscript">
      {chunks.map((chunk, index) => (
        <li className="pi-manuscript__chunk" key={`${chunk.index ?? "chunk"}-${index}`}>
          <span className="pi-manuscript__number" aria-hidden="true">
            {String(chunk.index ?? index + 1).padStart(3, "0")}
          </span>
          <div className="pi-manuscript__body">
            {chunk.excerpt.length > 0 ? (
              <p className="pi-manuscript__excerpt">{chunk.excerpt}</p>
            ) : (
              <p className="pi-manuscript__excerpt is-muted">
                No inline excerpt for this chunk.
              </p>
            )}
            <div className="pi-manuscript__meta">
              <span>chunk {chunk.index ?? index + 1}</span>
              {chunk.chars !== null ? <span>{formatNumber(chunk.chars)} chars</span> : null}
              {chunk.tokens !== null ? <span>{formatNumber(chunk.tokens)} tokens</span> : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function viewerPathFor(fileId: number | null, chunk: number | null): string | null {
  if (fileId === null) {
    return null;
  }
  if (chunk === null) {
    return "/viewer/file/" + fileId;
  }
  return "/viewer/file/" + fileId + "?chunk=" + chunk;
}

/** `read_file`: a manuscript window with the real file renderer underneath. */
export function ReadFilePanel({ item }: PanelProps) {
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Opening the requested chunk window." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="layers"
        title="The chunk window could not be read"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  const data = item.data;
  const fileId =
    recordId(data, "file_id") ??
    recordId(item.arguments, "file_id") ??
    (item.resource?.resourceType === "file" ? item.resource.resourceId : null);
  const chunks = chunksOf(data);
  const start =
    numberField(data, "chunk_start") ??
    numberField(item.arguments, "chunk") ??
    chunks[0]?.index ??
    null;
  const end = numberField(data, "chunk_end") ?? chunks.at(-1)?.index ?? start;
  const path = textField(data, "raw_file_path") ?? textField(data, "file_name");
  const viewerPath = viewerPathFor(fileId, start);

  return (
    <div className="pi-readfile">
      <header className="pi-readfile__head">
        <div>
          <p className="eyebrow">Manuscript window</p>
          <strong>{textField(data, "file_name") ?? path ?? "File leaf"}</strong>
          {path ? <code>{path}</code> : null}
        </div>
        {start !== null ? (
          <span className="pi-readfile__range">
            chunk {formatNumber(start)}
            {end !== null && end !== start ? `–${formatNumber(end)}` : ""}
            {numberField(data, "total_chunks") !== null
              ? ` / ${formatNumber(numberField(data, "total_chunks") ?? 0)}`
              : ""}
          </span>
        ) : null}
      </header>

      <ChunkWindow chunks={chunks} />

      {fileId !== null ? (
        <InspectorFileStage fileId={fileId} chunk={start} />
      ) : (
        <PanelEmpty
          icon="layers"
          title="No file id in this result"
          detail="The chunk excerpts above are all the inspector received."
        />
      )}

      {viewerPath ? (
        <PanelLink to={viewerPath}>Open the full file leaf</PanelLink>
      ) : null}
    </div>
  );
}
