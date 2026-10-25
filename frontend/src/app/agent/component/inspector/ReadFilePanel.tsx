import { truncate } from "../../../../lib/format";
import { CopyButton } from "../../../component/CopyButton";
import { useI18n } from "../../../i18n";
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
  readonly content: string;
}

function chunksOf(data: Record<string, unknown> | null): ChunkRecord[] {
  return recordList(data?.chunks).map((record) => {
    const content = textField(record, "content") ?? textField(record, "excerpt") ?? "";
    const excerpt = textField(record, "excerpt") ?? content;
    return {
      index: numberField(record, "chunk"),
      chars: numberField(record, "char_count"),
      tokens: numberField(record, "token_count"),
      excerpt: excerpt.length > 520 ? `${truncate(excerpt, 520)}` : excerpt,
      content,
    };
  });
}

function ChunkWindow({ chunks }: { readonly chunks: readonly ChunkRecord[] }) {
  const { t, formatNumber } = useI18n();
  if (chunks.length === 0) {
    return (
      <p className="pi-manuscript__quiet">
        {t("chat.panels.file.metadataOnly")}
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
                {t("chat.panels.file.noExcerpt")}
              </p>
            )}
            <div className="pi-manuscript__meta">
              <span>
                {t("chat.common.chunk", { chunk: chunk.index ?? index + 1 })}
              </span>
              {chunk.chars !== null ? (
                <span>
                  {t("chat.panels.file.chars", {
                    count: formatNumber(chunk.chars),
                  })}
                </span>
              ) : null}
              {chunk.tokens !== null ? (
                <span>
                  {t("chat.panels.file.tokens", {
                    count: formatNumber(chunk.tokens),
                  })}
                </span>
              ) : null}
              <CopyButton
                value={chunk.content || chunk.excerpt}
                label={t("chat.panels.file.copyChunk")}
                iconOnly
                title={t("chat.panels.file.copyChunkTitle", {
                  index: chunk.index ?? index + 1,
                })}
              />
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
    return "/library?tab=files&file=" + fileId;
  }
  return "/library?tab=files&file=" + fileId + "&chunk=" + chunk;
}

/** `read_file`: a manuscript window with the real file renderer underneath. */
export function ReadFilePanel({ item }: PanelProps) {
  const { t, formatNumber } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return (
      <LivePanel item={item} detail={t("chat.panels.file.liveDetail")} />
    );
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="layers"
        title={t("chat.panels.file.errorTitle")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
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
          <p className="eyebrow">{t("chat.panels.file.manuscript")}</p>
          <strong>
            {textField(data, "file_name") ??
              path ??
              t("chat.panels.file.fileLeaf")}
          </strong>
          {path ? <code>{path}</code> : null}
        </div>
        {start !== null ? (
          <span className="pi-readfile__range">
            {t("chat.common.chunk", { chunk: formatNumber(start) })}
            {end !== null && end !== start
              ? `–${formatNumber(end)}`
              : ""}
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
          title={t("chat.panels.file.noFileIdTitle")}
          detail={t("chat.panels.file.noFileIdDetail")}
        />
      )}

      {viewerPath ? (
        <PanelLink to={viewerPath}>{t("chat.panels.file.openFull")}</PanelLink>
      ) : null}
    </div>
  );
}
