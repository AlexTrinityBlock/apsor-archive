import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { libraryMemoryUrl } from "../../../../lib/library-url";
import { MemoryStatus } from "../../../component/memory/MemoryStatus";
import {
  useListFileRelatedMemories,
  useListRelatedMemories,
} from "../../../generated-apis-types/memories/memories";
import type {
  RelatedMemoriesSchema,
  RelatedMemorySchema,
} from "../../../generated-apis-types/schemas";
import { useI18n } from "../../../i18n";
import { MemoryErrorState, MemorySkeleton } from "./MemoryStates";
import {
  clipRelatedPreview,
  orderRelatedReasons,
  relatedReasonKey,
} from "./related-memories";
import "./related-memories.css";

export type RelatedMemoriesSource =
  | { readonly kind: "memory"; readonly memoryId: number }
  | {
      readonly kind: "file";
      readonly fileId: number;
      /** Historical or deleted versions have no related list. */
      readonly historical: boolean;
    };

const RELATED_LIMIT = 6;

function RelatedRow({ item }: { readonly item: RelatedMemorySchema }) {
  const { t, formatDate } = useI18n();
  const { memory } = item;
  const reasons = orderRelatedReasons(item.reasons);
  return (
    <li>
      <Link
        className={[
          "related-memory",
          memory.status === "deprecated" ? "is-deprecated" : null,
        ]
          .filter(Boolean)
          .join(" ")}
        to={libraryMemoryUrl(memory.memory_id)}
        title={t("memory.related.scoreTitle", { score: item.score.toFixed(4) })}
      >
        <span className="related-memory__head">
          <span className="related-memory__title">{memory.title}</span>
          <MemoryStatus status={memory.status} small />
        </span>
        <span className="related-memory__preview">
          {clipRelatedPreview(memory.content)}
        </span>
        <span className="related-memory__foot">
          <time dateTime={memory.update_time}>{formatDate(memory.update_time)}</time>
          {reasons.map((reason) => (
            <span className="related-memory__chip" key={reason}>
              {t(relatedReasonKey(reason))}
            </span>
          ))}
        </span>
      </Link>
    </li>
  );
}

function RelatedBody({
  data,
  isLoading,
  error,
  onRetry,
}: {
  readonly data: RelatedMemoriesSchema | undefined;
  readonly isLoading: boolean;
  readonly error: unknown;
  readonly onRetry: () => void;
}) {
  const { t } = useI18n();
  if (isLoading) {
    return <MemorySkeleton label={t("memory.related.loading")} count={3} />;
  }
  if (error || !data) {
    return (
      <MemoryErrorState
        title={t("memory.related.error")}
        description={t("memory.related.description")}
        error={error}
        onRetry={onRetry}
      />
    );
  }
  return (
    <>
      {data.similarity_available ? null : (
        <p className="related-memories__note">{t("memory.related.similarityUnavailable")}</p>
      )}
      {data.resources.length === 0 ? (
        <p className="related-memories__note">{t("memory.related.empty")}</p>
      ) : (
        <ul className="related-memories__list">
          {data.resources.map((item) => (
            <RelatedRow key={item.memory.memory_id} item={item} />
          ))}
        </ul>
      )}
    </>
  );
}

function MemoryRelated({ memoryId }: { readonly memoryId: number }) {
  const { t } = useI18n();
  const toggleId = useId();
  const [includeDeprecated, setIncludeDeprecated] = useState(false);
  const query = useListRelatedMemories(memoryId, {
    limit: RELATED_LIMIT,
    include_deprecated: includeDeprecated,
  });
  return (
    <>
      <label className="related-memories__toggle" htmlFor={toggleId}>
        <input
          id={toggleId}
          type="checkbox"
          checked={includeDeprecated}
          onChange={(event) => setIncludeDeprecated(event.target.checked)}
        />
        {t("memory.related.showDeprecated")}
      </label>
      <RelatedBody
        data={query.data}
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    </>
  );
}

function FileRelated({
  fileId,
  historical,
}: {
  readonly fileId: number;
  readonly historical: boolean;
}) {
  const { t } = useI18n();
  const query = useListFileRelatedMemories(
    fileId,
    { limit: RELATED_LIMIT },
    { query: { enabled: !historical } },
  );
  if (historical) {
    return <p className="related-memories__note">{t("library.preview.relatedMemoriesHistorical")}</p>;
  }
  return (
    <RelatedBody
      data={query.data}
      isLoading={query.isLoading}
      error={query.error}
      onRetry={() => void query.refetch()}
    />
  );
}

/**
 * 關聯記憶 — memories related to a memory or a file, ranked by stored
 * similarity, shared keywords, and shared summaries. The memory reader shows
 * it between the record and its lineage; the file preview shows it on the
 * Metadata tab, which mounts it only while that tab is open.
 */
export function RelatedMemories({ source }: { readonly source: RelatedMemoriesSource }) {
  const { t } = useI18n();
  const headingId = useId();
  return (
    <section className="related-memories" aria-labelledby={headingId}>
      <header className="related-memories__header">
        <h3 className="related-memories__title" id={headingId}>
          {source.kind === "file"
            ? t("library.preview.relatedMemoriesTitle")
            : t("memory.related.title")}
        </h3>
        <p className="related-memories__description">{t("memory.related.description")}</p>
      </header>
      {source.kind === "memory" ? (
        <MemoryRelated memoryId={source.memoryId} />
      ) : (
        <FileRelated fileId={source.fileId} historical={source.historical} />
      )}
    </section>
  );
}
