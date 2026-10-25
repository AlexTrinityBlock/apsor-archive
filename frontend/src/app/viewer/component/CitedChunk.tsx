import { Link } from "react-router-dom";

import { useReadFile } from "../../generated-apis-types/files/files";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface CitedChunkProps {
  readonly fileId: number;
  readonly chunk: number;
}

/** A compact cited-passage card for `?chunk=N` deep links from the agent. */
export function CitedChunk({ fileId, chunk }: CitedChunkProps) {
  const { t, formatNumber } = useI18n();
  const query = useReadFile(fileId, chunk, { chunk_range: 0 }, { query: { retry: false } });

  return (
    <aside
      className="viewer-citation"
      aria-label={t("library.viewer.citation.aria", { chunk })}
    >
      <div className="viewer-citation__head">
        <span className="eyebrow">
          <Icon name="quote" size={13} />{" "}
          {t("library.viewer.citation.eyebrow", { chunk })}
        </span>
        <Link to={`/library?tab=files&file=${fileId}`} className="viewer-citation__clear">
          {t("library.viewer.citation.openInLibrary")}
        </Link>
      </div>
      {query.isLoading ? (
        <p className="viewer-citation__note">{t("library.viewer.citation.loading")}</p>
      ) : null}
      {query.error ? (
        <p className="viewer-citation__note">
          {t("library.viewer.citation.outside", { chunk })}
        </p>
      ) : null}
      {query.data ? (
        <>
          <pre className="viewer-citation__text">
            {query.data.chunks[0]?.content ?? t("library.viewer.citation.empty")}
          </pre>
          <p className="viewer-citation__meta">
            {t("library.viewer.citation.meta", {
              chars: formatNumber(query.data.chunks[0]?.char_count ?? 0),
              start: query.data.chunk_start,
              end: query.data.chunk_end,
              total: formatNumber(query.data.total_chunks),
            })}
          </p>
        </>
      ) : null}
    </aside>
  );
}
