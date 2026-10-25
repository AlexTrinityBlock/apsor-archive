import { useState } from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
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
  const { t, formatNumber } = useI18n();
  const [wrap, setWrap] = useState(true);
  const query = useChunkedText(fileId, totalChunks, totalChunks > 0);

  if (totalChunks === 0) {
    return (
      <ViewerErrorState
        error={new Error(reason)}
        title={t("library.viewer.fallback.errorTitle")}
      />
    );
  }

  if (query.isLoading) {
    return <ViewerLoading label={t("library.viewer.loading.reassembling")} />;
  }

  if (query.error) {
    return (
      <ViewerErrorState
        error={query.error}
        title={t("library.viewer.fallback.readError")}
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
          {t(
            query.data.chunkCount === 1
              ? "library.viewer.fallback.noticeOne"
              : "library.viewer.fallback.noticeOther",
            {
              reason,
              count: formatNumber(query.data.chunkCount),
            },
          )}
        </p>
        <Button variant="ghost" size="sm" onClick={() => setWrap((current) => !current)}>
          {wrap ? t("library.viewer.text.noWrap") : t("library.viewer.text.wrap")}
        </Button>
      </div>
      <pre className={wrap ? "viewer-pre is-wrapped" : "viewer-pre"}>{query.data.text}</pre>
    </div>
  );
}
