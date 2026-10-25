import type { PathFileSchema } from "../../generated-apis-types/schemas";
import { getGetFileContentUrl } from "../../generated-apis-types/files/files";
import { formatBytes } from "../../../lib/format";
import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { fileKindLabel } from "./library-utils";

interface LibraryMediaGalleryProps {
  readonly path: string;
  readonly images: readonly PathFileSchema[];
  readonly totalImages: number;
  readonly filter: string;
  readonly onFilterChange: (value: string) => void;
  readonly onClearFilter: () => void;
  readonly onOpen: (fileId: number) => void;
  readonly onUploadImage: () => void;
  readonly onOpenRoot: () => void;
}

interface MediaToolbarProps {
  readonly images: number;
  readonly totalImages: number;
  readonly filter: string;
  readonly onFilterChange: (value: string) => void;
  readonly onClearFilter: () => void;
  readonly onUploadImage: () => void;
}

interface MediaCardProps {
  readonly file: PathFileSchema;
  readonly onOpen: (fileId: number) => void;
}

function MediaToolbar({
  images,
  totalImages,
  filter,
  onFilterChange,
  onClearFilter,
  onUploadImage,
}: MediaToolbarProps) {
  const { t, formatNumber } = useI18n();
  const hasFilter = filter.trim().length > 0;
  const countLabel = t(
    totalImages === 1 ? "library.units.imageOne" : "library.units.imageOther",
    { count: formatNumber(totalImages) },
  );
  const statusLabel = hasFilter
    ? t("library.media.filteredStatus", {
        shown: formatNumber(images),
        total: formatNumber(totalImages),
      })
    : countLabel;

  return (
    <div className="library-media-toolbar">
      <div className="library-search-mini library-media-toolbar__filter">
        <span className="library-search-mini__icon" aria-hidden="true">
          <Icon name="search" size={14} />
        </span>
        <label className="visually-hidden" htmlFor="library-media-filter">
          {t("library.media.filterLabel")}
        </label>
        <input
          id="library-media-filter"
          type="search"
          value={filter}
          onChange={(event) => onFilterChange(event.target.value)}
          placeholder={t("library.media.filterPlaceholder")}
          autoComplete="off"
          spellCheck={false}
        />
        {hasFilter ? (
          <button
            type="button"
            className="library-search-mini__clear"
            onClick={onClearFilter}
            aria-label={t("library.media.clearFilterAria")}
          >
            <Icon name="close" size={13} />
          </button>
        ) : null}
      </div>

      <span className="library-media-toolbar__status" aria-live="polite">
        {statusLabel}
      </span>

      <div className="library-media-toolbar__actions">
        <Button variant="secondary" size="sm" onClick={onClearFilter} disabled={!hasFilter}>
          {t("library.common.clear")}
        </Button>
        <Button variant="primary" size="sm" onClick={onUploadImage}>
          <Icon name="plus" size={14} />
          {t("library.media.uploadImage")}
        </Button>
      </div>
    </div>
  );
}

function MediaCard({ file, onOpen }: MediaCardProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  return (
    <article className="library-media-card">
      <button
        type="button"
        className="library-media-card__open"
        onClick={() => onOpen(file.file_id)}
        aria-label={t("library.media.previewImage", { name: file.file_name })}
      >
        <span className="library-media-card__figure">
          <img
            src={getGetFileContentUrl(file.file_id)}
            alt={file.file_name}
            loading="lazy"
            decoding="async"
          />
          <span className="file-type-pill library-media-card__type">
            {fileKindLabel(file.file_name)}
          </span>
        </span>
        <span className="library-media-card__body">
          <span className="library-media-card__name">{file.file_name}</span>
          <span className="library-media-card__meta">
            {formatBytes(file.size_bytes)} ·{" "}
            {t(
              file.total_chunks === 1
                ? "library.units.chunkOne"
                : "library.units.chunkOther",
              { count: formatNumber(file.total_chunks) },
            )}
          </span>
          <code className="library-media-card__path">{file.raw_file_path}</code>
          <time className="library-media-card__time" dateTime={file.update_time}>
            {formatDateTime(file.update_time)}
          </time>
        </span>
      </button>
    </article>
  );
}

function MediaResults({
  path,
  images,
  totalImages,
  filter,
  onClearFilter,
  onOpen,
  onUploadImage,
  onOpenRoot,
}: Omit<LibraryMediaGalleryProps, "onFilterChange">) {
  const { t } = useI18n();
  if (totalImages === 0) {
    return (
      <EmptyState
        icon="ring"
        eyebrow={t("library.media.eyebrow")}
        title={t("library.media.emptyTitle")}
        description={t("library.media.emptyDescription")}
        className="library-media__empty"
        action={
          <div className="empty-state__actions">
            <Button variant="ink" size="sm" onClick={onUploadImage}>
              <Icon name="plus" size={15} />
              {t("library.media.uploadImage")}
            </Button>
            {path !== "/" ? (
              <Button variant="ghost" size="sm" onClick={onOpenRoot}>
                {t("library.common.backToRoot")}
              </Button>
            ) : null}
          </div>
        }
      />
    );
  }
  if (images.length === 0) {
    return (
      <EmptyState
        icon="search"
        eyebrow={t("library.media.filterEyebrow")}
        title={t("library.media.noMatchTitle", { query: filter.trim() })}
        description={t("library.media.noMatchDescription")}
        className="library-media__empty"
        action={
          <Button variant="secondary" size="sm" onClick={onClearFilter}>
            {t("library.media.clearFilter")}
          </Button>
        }
      />
    );
  }
  return (
    <div className="library-media-grid">
      {images.map((file) => (
        <MediaCard key={file.file_id} file={file} onOpen={onOpen} />
      ))}
    </div>
  );
}

/**
 * Image-only view over the same path listing the Files tab uses. There is no
 * media API, no visual search, and no invented caption: thumbnails are the
 * stored file content and all metadata comes from `PathFileSchema`.
 */
export function LibraryMediaGallery({
  path,
  images,
  totalImages,
  filter,
  onFilterChange,
  onClearFilter,
  onOpen,
  onUploadImage,
  onOpenRoot,
}: LibraryMediaGalleryProps) {
  const { t } = useI18n();
  return (
    <section className="library-media" aria-label={t("library.media.aria")}>
      <MediaToolbar
        images={images.length}
        totalImages={totalImages}
        filter={filter}
        onFilterChange={onFilterChange}
        onClearFilter={onClearFilter}
        onUploadImage={onUploadImage}
      />
      <MediaResults
        path={path}
        images={images}
        totalImages={totalImages}
        filter={filter}
        onClearFilter={onClearFilter}
        onOpen={onOpen}
        onUploadImage={onUploadImage}
        onOpenRoot={onOpenRoot}
      />
    </section>
  );
}
