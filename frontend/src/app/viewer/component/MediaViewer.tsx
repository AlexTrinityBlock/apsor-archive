import { useMemo, useState } from "react";
import { useGetMedia, getGetMediaContentUrl, useListMedia } from "../../generated-apis-types/media/media";
import Lightbox from "yet-another-react-lightbox";
import "yet-another-react-lightbox/styles.css";

import { formatBytes, formatDateTime } from "../../../lib/format";
import {
  mediaAltText,
  mediaDimensions,
  mediaDisplayTitle,
  mediaDocumentType,
} from "../../media/component/media-utils";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { ImageView } from "./ImageView";
import { ViewerErrorState, ViewerLoading, ViewerMissing } from "./ViewerStates";
import { ViewerShell } from "./ViewerShell";
import { viewerErrorStatus } from "./viewer-utils";

/**
 * The standalone media viewer for `/viewer/media/:mediaId`.
 *
 * The stage uses the native `<img>` element plus zoom/pan controls. A recent
 * media rail opens the same images in `yet-another-react-lightbox`, so the
 * gallery path works without leaving the viewer.
 */
export function MediaViewer({ mediaId }: { readonly mediaId: number }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const mediaQuery = useGetMedia(mediaId, { query: { retry: false } });
  const recentQuery = useListMedia({ limit: 24, offset: 0 });
  const media = mediaQuery.data;

  const gallery = useMemo(() => {
    const recent = recentQuery.data?.resources ?? [];
    if (!media) {
      return recent;
    }
    if (recent.some((item) => item.media_id === media.media_id)) {
      return recent;
    }
    return [media, ...recent];
  }, [media, recentQuery.data]);

  const slides = useMemo(
    () =>
      gallery.map((item) => ({
        src: getGetMediaContentUrl(item.media_id),
        alt: mediaAltText(item),
      })),
    [gallery],
  );

  const status = viewerErrorStatus(mediaQuery.error);

  if (mediaQuery.isLoading) {
    return (
      <ViewerShell
        kind="Media specimen"
        title={`Reading image #${mediaId}`}
        backTo="/media"
        backLabel="Media index"
      >
        <ViewerLoading label="Reading the specimen sheet" />
      </ViewerShell>
    );
  }

  if (mediaQuery.error || !media) {
    return (
      <ViewerShell
        kind="Media specimen"
        title={`Image #${mediaId}`}
        backTo="/media"
        backLabel="Media index"
      >
        {status === 404 ? (
          <ViewerMissing
            title="This specimen is not in the media index."
            message={`Image #${mediaId} may have been deleted or never ingested. The media index keeps no anonymous objects.`}
            backTo="/media"
            backLabel="Back to the media index"
          />
        ) : (
          <ViewerErrorState
            error={mediaQuery.error}
            title="The media metadata could not be read"
            onRetry={() => void mediaQuery.refetch()}
          />
        )}
      </ViewerShell>
    );
  }

  const contentUrl = getGetMediaContentUrl(media.media_id);
  const title = mediaDisplayTitle(media);
  const currentIndex = Math.max(
    0,
    gallery.findIndex((item) => item.media_id === media.media_id),
  );
  const openGallery = (index: number) => {
    setLightboxIndex(index);
    setLightboxOpen(true);
  };

  return (
    <ViewerShell
      kind={`Media specimen · ${mediaDocumentType(media)}`}
      title={title}
      path={media.raw_file_path}
      backTo="/media"
      backLabel="Media index"
      actions={
        <>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => openGallery(currentIndex)}
          >
            <Icon name="layers" size={15} />
            <span>Gallery</span>
          </button>
          <a
            className="btn btn--ghost btn--sm"
            href={contentUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Icon name="external" size={15} />
            <span>Open original</span>
          </a>
          <a
            className="btn btn--secondary btn--sm"
            href={contentUrl}
            download={media.file_name}
          >
            <Icon name="arrow-down" size={15} />
            <span>Download</span>
          </a>
        </>
      }
      meta={
        <>
          <Badge tone="moss" dot>
            {media.mime_type.replace("image/", "").toUpperCase()}
          </Badge>
          <Badge tone="neutral">{mediaDimensions(media)}</Badge>
          <Badge tone="neutral">{formatBytes(media.size_bytes)}</Badge>
          <Badge tone="neutral">#{media.media_id}</Badge>
        </>
      }
    >
      <div className="viewer-media">
        <div className="viewer-media__stage">
          <ImageView
            src={contentUrl}
            alt={mediaAltText(media)}
            downloadUrl={contentUrl}
            downloadName={media.file_name}
          />
          {gallery.length > 1 ? (
            <div className="viewer-media__rail" aria-label="Recent media">
              {gallery.slice(0, 12).map((item, index) => {
                const selected = item.media_id === media.media_id;
                return (
                  <button
                    type="button"
                    key={item.media_id}
                    className={selected ? "viewer-media__thumb is-current" : "viewer-media__thumb"}
                    onClick={() => openGallery(index)}
                    aria-label={`Open ${mediaDisplayTitle(item)} in the gallery`}
                    aria-current={selected ? "true" : undefined}
                  >
                    <img
                      src={getGetMediaContentUrl(item.media_id)}
                      alt=""
                      loading="lazy"
                      decoding="async"
                    />
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>

        <aside className="viewer-media__notes" aria-label="Specimen notes">
          <section className="viewer-media__section">
            <p className="eyebrow">Caption</p>
            <p className="viewer-media__prose">
              {media.caption.trim().length > 0
                ? media.caption
                : "No caption has been written for this image."}
            </p>
          </section>

          {media.summary.trim().length > 0 ? (
            <section className="viewer-media__section">
              <p className="eyebrow">Summary</p>
              <p className="viewer-media__prose">{media.summary}</p>
            </section>
          ) : null}

          {media.ocr_text.trim().length > 0 ? (
            <section className="viewer-media__section">
              <p className="eyebrow">OCR text</p>
              <pre className="viewer-pre viewer-pre--compact is-wrapped">{media.ocr_text}</pre>
            </section>
          ) : null}

          {media.tags.length > 0 ? (
            <section className="viewer-media__section">
              <p className="eyebrow">Tags</p>
              <ul className="viewer-media__tags">
                {media.tags.map((tag, index) => (
                  <li key={`${tag}-${index}`}>#{tag}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="viewer-media__section">
            <p className="eyebrow">Archive record</p>
            <dl className="viewer-media__meta">
              <div>
                <dt>Media id</dt>
                <dd>#{media.media_id}</dd>
              </div>
              <div>
                <dt>Document type</dt>
                <dd>{mediaDocumentType(media)}</dd>
              </div>
              <div>
                <dt>Dimensions</dt>
                <dd>{mediaDimensions(media)}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>
                  <time dateTime={media.update_time}>{formatDateTime(media.update_time)}</time>
                </dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>
                  <time dateTime={media.created_at}>{formatDateTime(media.created_at)}</time>
                </dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>

      <Lightbox
        open={lightboxOpen}
        close={() => setLightboxOpen(false)}
        index={lightboxIndex}
        slides={slides}
      />
    </ViewerShell>
  );
}
