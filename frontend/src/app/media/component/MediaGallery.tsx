import { useId } from "react";

import type { MediaSchema, MediaSearchResultSchema } from "../../generated-apis-types/schemas";
import { getGetMediaContentUrl } from "../../generated-apis-types/media/media";
import { formatDateTime } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import {
  formatMediaScore,
  mediaAltText,
  mediaCaptionExcerpt,
  mediaDimensions,
  mediaDisplayTitle,
  mediaDocumentType,
} from "./media-utils";

export type MediaGalleryItem = MediaSchema &
  Partial<Pick<MediaSearchResultSchema, "score" | "matched_by">>;

export type MediaGalleryMode = "archive" | "text" | "visual";

interface MediaGalleryProps {
  readonly items: readonly MediaGalleryItem[];
  readonly total: number;
  readonly mode: MediaGalleryMode;
  readonly query?: string;
  readonly elapsedMs?: number;
  readonly onSelect: (media: MediaSchema) => void;
}

interface MediaCardProps {
  readonly media: MediaGalleryItem;
  readonly onSelect: (media: MediaSchema) => void;
}

function cardMeta(mode: MediaGalleryMode): { readonly eyebrow: string; readonly title: string } {
  if (mode === "text") {
    return { eyebrow: "Text to image · captions, OCR, tags", title: "Text matches" };
  }
  if (mode === "visual") {
    return { eyebrow: "Image to image · visual similarity", title: "Visual neighbours" };
  }
  return { eyebrow: "Visual archive · standalone index", title: "Specimen sheets" };
}

function GalleryNote({ mode, query }: { readonly mode: MediaGalleryMode; readonly query?: string }) {
  if (mode === "text" && query) {
    return (
      <p className="media-gallery__note">
        Matching captions, tags, and OCR text for <code>“{query}”</code>.
      </p>
    );
  }
  if (mode === "visual") {
    return (
      <p className="media-gallery__note">
        Ordered by visual fingerprint similarity to the query image.
      </p>
    );
  }
  return (
    <p className="media-gallery__note">
      A separate visual index. These images never appear as text chunks.
    </p>
  );
}

function MediaCard({ media, onSelect }: MediaCardProps) {
  const title = mediaDisplayTitle(media);
  const caption = mediaCaptionExcerpt(media);
  const documentType = mediaDocumentType(media);
  const dimensions = mediaDimensions(media);
  const hasMatch = typeof media.score === "number" && media.matched_by !== undefined;
  const matchLabel = media.matched_by === "visual" ? "VISUAL" : "TEXT";
  const matchTone = media.matched_by === "visual" ? "ochre" : "moss";
  const scoreLabel =
    hasMatch && typeof media.score === "number"
      ? `, ${matchLabel} score ${formatMediaScore(media.score)}`
      : "";

  return (
    <article className="media-card">
      <button
        type="button"
        className="media-card__open"
        onClick={() => onSelect(media)}
        aria-label={`Open ${title}. ${documentType}, ${dimensions}${scoreLabel}.`}
      >
        <span className="media-card__figure">
          <img
            className="media-card__image"
            src={getGetMediaContentUrl(media.media_id)}
            alt={mediaAltText(media)}
            loading="lazy"
            decoding="async"
          />
          <span className="media-card__corner media-card__corner--tl" aria-hidden="true" />
          <span className="media-card__corner media-card__corner--tr" aria-hidden="true" />
          <span className="media-card__corner media-card__corner--bl" aria-hidden="true" />
          <span className="media-card__corner media-card__corner--br" aria-hidden="true" />
          <span className="media-card__type">{documentType}</span>
          {hasMatch && typeof media.score === "number" ? (
            <span className="media-card__match">
              <Badge tone={matchTone}>{matchLabel}</Badge>
              <span className="media-card__score">
                score {formatMediaScore(media.score)}
              </span>
            </span>
          ) : null}
        </span>

        <span className="media-card__body">
          <span className="media-card__meta">
            <span>{documentType}</span>
            <span aria-hidden="true">·</span>
            <span>{dimensions}</span>
          </span>
          <span className="media-card__title">{title}</span>
          {caption ? <span className="media-card__caption">{caption}</span> : null}
          {media.tags.length > 0 ? (
            <span className="media-card__tags">
              {media.tags.slice(0, 3).map((tag, index) => (
                <span className="media-card__tag" key={`${tag}-${index}`}>
                  #{tag}
                </span>
              ))}
              {media.tags.length > 3 ? (
                <span className="media-card__tag media-card__tag--more">
                  +{media.tags.length - 3}
                </span>
              ) : null}
            </span>
          ) : null}
          <span className="media-card__foot">
            <time dateTime={media.update_time}>{formatDateTime(media.update_time)}</time>
            <span className="media-card__index">#{media.media_id}</span>
          </span>
        </span>
      </button>
    </article>
  );
}

/**
 * A specimen-sheet grid. Card images are the hero; metadata sits beneath thin
 * rules, and search score / match mode only appear when a search produced the
 * result.
 */
export function MediaGallery({
  items,
  total,
  mode,
  query,
  elapsedMs,
  onSelect,
}: MediaGalleryProps) {
  const headingId = useId();
  const meta = cardMeta(mode);
  const countLabel = `${total} ${total === 1 ? "image" : "images"}`;

  return (
    <section className="media-gallery reveal reveal-3" aria-labelledby={headingId}>
      <header className="media-gallery__head">
        <div className="media-gallery__heading">
          <p className="eyebrow">{meta.eyebrow}</p>
          <h2 className="media-gallery__title" id={headingId}>
            {meta.title}
          </h2>
          <GalleryNote mode={mode} query={query} />
        </div>
        <div className="media-gallery__stats">
          <Badge tone={mode === "archive" ? "moss" : "ochre"} dot>
            {countLabel}
          </Badge>
          {typeof elapsedMs === "number" ? (
            <span className="media-gallery__elapsed">{elapsedMs} ms</span>
          ) : null}
          <span className="media-gallery__index">
            <Icon name="ring" size={13} />
            media index
          </span>
        </div>
      </header>

      <ul className="media-grid">
        {items.map((media) => (
          <li key={media.media_id} className="media-grid__item">
            <MediaCard media={media} onSelect={onSelect} />
          </li>
        ))}
      </ul>
    </section>
  );
}
