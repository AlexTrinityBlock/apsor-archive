import type { PathFileSchema } from "../../generated-apis-types/schemas";
import { getGetFileContentUrl } from "../../generated-apis-types/files/files";
import { formatBytes, formatDateTime } from "../../../lib/format";
import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";
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
  const hasFilter = filter.trim().length > 0;
  const countLabel = `${totalImages} ${totalImages === 1 ? "image" : "images"}`;
  const statusLabel = hasFilter ? `${images} of ${totalImages} images` : countLabel;

  return (
    <div className="library-media-toolbar">
      <div className="library-search-mini library-media-toolbar__filter">
        <span className="library-search-mini__icon" aria-hidden="true">
          <Icon name="search" size={14} />
        </span>
        <label className="visually-hidden" htmlFor="library-media-filter">
          Filter images by name or path
        </label>
        <input
          id="library-media-filter"
          type="search"
          value={filter}
          onChange={(event) => onFilterChange(event.target.value)}
          placeholder="Filter images by name or path…"
          autoComplete="off"
          spellCheck={false}
        />
        {hasFilter ? (
          <button
            type="button"
            className="library-search-mini__clear"
            onClick={onClearFilter}
            aria-label="Clear image filter"
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
          Clear
        </Button>
        <Button variant="primary" size="sm" onClick={onUploadImage}>
          <Icon name="plus" size={14} />
          Upload image
        </Button>
      </div>
    </div>
  );
}

function MediaCard({ file, onOpen }: MediaCardProps) {
  return (
    <article className="library-media-card">
      <button
        type="button"
        className="library-media-card__open"
        onClick={() => onOpen(file.file_id)}
        aria-label={`Preview ${file.file_name}`}
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
            {formatBytes(file.size_bytes)} · {file.total_chunks}{" "}
            {file.total_chunks === 1 ? "chunk" : "chunks"}
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
  if (totalImages === 0) {
    return (
      <EmptyState
        icon="ring"
        eyebrow="Media gallery"
        title="No images in this folder."
        description="Images are ordinary files. Upload a JPEG, PNG, or WebP through the file ingest queue and it appears here as a thumbnail."
        className="library-media__empty"
        action={
          <div className="empty-state__actions">
            <Button variant="ink" size="sm" onClick={onUploadImage}>
              <Icon name="plus" size={15} />
              Upload image
            </Button>
            {path !== "/" ? (
              <Button variant="ghost" size="sm" onClick={onOpenRoot}>
                Back to archive root
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
        eyebrow="Image filter"
        title={`No images match “${filter.trim()}”.`}
        description="Try fewer characters or another fragment of the file name or path."
        className="library-media__empty"
        action={
          <Button variant="secondary" size="sm" onClick={onClearFilter}>
            Clear filter
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
  return (
    <section className="library-media" aria-label="Media gallery">
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
