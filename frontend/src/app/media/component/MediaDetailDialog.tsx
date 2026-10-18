import { useEffect, useId, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import type { MediaSchema } from "../../generated-apis-types/schemas";
import {
  getGetMediaContentUrl,
  useDeleteMedia,
  useDescribeMedia,
} from "../../generated-apis-types/media/media";
import { formatBytes, formatDateTime } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button, buttonClassName } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { MediaDialog } from "./MediaDialog";
import {
  isCaptionFailure,
  isProviderUnavailable,
  mediaAltText,
  mediaDimensions,
  mediaDisplayTitle,
  mediaDocumentType,
  mediaErrorMessage,
} from "./media-utils";

interface MediaDetailDialogProps {
  readonly media: MediaSchema;
  readonly onClose: () => void;
  readonly onUpdated: (media: MediaSchema) => void;
  readonly onDeleted: () => void;
}

/**
 * One specimen sheet at full size: the image, its generated text, the archive
 * metadata, and the two mutations that can change it. Delete asks for an
 * explicit second confirmation inside the same modal.
 */
export function MediaDetailDialog({
  media,
  onClose,
  onUpdated,
  onDeleted,
}: MediaDetailDialogProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const deleteHeadingId = useId();
  const deleteActionId = `media-delete-action-${media.media_id}`;
  const confirmRef = useRef<HTMLDivElement>(null);
  const wasConfirming = useRef(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (confirmingDelete) {
      confirmRef.current?.focus();
    } else if (wasConfirming.current) {
      document.getElementById(deleteActionId)?.focus();
    }
    wasConfirming.current = confirmingDelete;
  }, [confirmingDelete, deleteActionId]);

  const describeMutation = useDescribeMedia({
    mutation: {
      onSuccess: (updated) => {
        onUpdated(updated);
        toast.success("Caption, OCR, title, summary, and tags were refreshed from the image.");
        void queryClient.invalidateQueries();
      },
      onError: (error) => {
        toast.error(mediaErrorMessage(error));
      },
    },
  });

  const deleteMutation = useDeleteMedia({
    mutation: {
      onSuccess: () => {
        toast.success(`“${mediaDisplayTitle(media)}” was removed from the media index.`);
        void queryClient.invalidateQueries();
        onDeleted();
      },
    },
  });

  const title = mediaDisplayTitle(media);
  const documentType = mediaDocumentType(media);
  const contentUrl = getGetMediaContentUrl(media.media_id);
  const describePending = describeMutation.isPending;
  const deletePending = deleteMutation.isPending;
  const describeError = describeMutation.error;
  const deleteError = deleteMutation.error;

  return (
    <MediaDialog
      eyebrow="Media specimen · visual archive"
      title={title}
      description={`${documentType} · ${media.file_name}`}
      onClose={onClose}
      dismissible={!deletePending}
      className="media-detail-dialog"
      wide
    >
      <div className="media-detail">
        <figure className="media-detail__figure">
          <div className="media-detail__frame">
            <span className="media-detail__corner media-detail__corner--tl" aria-hidden="true" />
            <span className="media-detail__corner media-detail__corner--tr" aria-hidden="true" />
            <span className="media-detail__corner media-detail__corner--bl" aria-hidden="true" />
            <span className="media-detail__corner media-detail__corner--br" aria-hidden="true" />
            <img
              src={contentUrl}
              alt={mediaAltText(media)}
              className="media-detail__image"
              decoding="async"
            />
          </div>
          <figcaption className="media-detail__caption">
            <span>{media.mime_type}</span>
            <span aria-hidden="true">·</span>
            <span>{mediaDimensions(media)}</span>
            <span aria-hidden="true">·</span>
            <span>{formatBytes(media.size_bytes)}</span>
          </figcaption>
        </figure>

        <div className="media-detail__body">
          <div className="media-detail__badges">
            <Badge tone="moss" dot>
              {documentType}
            </Badge>
            <Badge tone="neutral">{media.mime_type.replace("image/", "").toUpperCase()}</Badge>
            <Badge tone="neutral">{formatBytes(media.size_bytes)}</Badge>
          </div>

          <dl className="media-detail__meta">
            <div>
              <dt>Dimensions</dt>
              <dd>{mediaDimensions(media)}</dd>
            </div>
            <div>
              <dt>Media ID</dt>
              <dd>#{media.media_id}</dd>
            </div>
            <div className="media-detail__meta-wide">
              <dt>Path</dt>
              <dd>
                <code>{media.raw_file_path}</code>
              </dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>
                <time dateTime={media.created_at}>{formatDateTime(media.created_at)}</time>
              </dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>
                <time dateTime={media.update_time}>{formatDateTime(media.update_time)}</time>
              </dd>
            </div>
          </dl>

          <section className="media-detail__section" aria-labelledby="media-detail-caption">
            <p className="eyebrow" id="media-detail-caption">
              Caption
            </p>
            <p className="media-detail__prose">
              {media.caption.trim().length > 0 ? media.caption : "No caption has been written yet."}
            </p>
          </section>

          {media.summary.trim().length > 0 ? (
            <section className="media-detail__section" aria-labelledby="media-detail-summary">
              <p className="eyebrow" id="media-detail-summary">
                Summary
              </p>
              <p className="media-detail__prose">{media.summary}</p>
            </section>
          ) : null}

          {media.ocr_text.trim().length > 0 ? (
            <section className="media-detail__section" aria-labelledby="media-detail-ocr">
              <p className="eyebrow" id="media-detail-ocr">
                OCR text
              </p>
              <pre className="media-detail__ocr">{media.ocr_text}</pre>
            </section>
          ) : null}

          {media.tags.length > 0 ? (
            <section className="media-detail__section" aria-labelledby="media-detail-tags">
              <p className="eyebrow" id="media-detail-tags">
                Tags
              </p>
              <ul className="media-detail__tags">
                {media.tags.map((tag, index) => (
                  <li key={`${tag}-${index}`}>#{tag}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="media-detail__actions">
            <a
              className={buttonClassName({ variant: "secondary", size: "sm" })}
              href={contentUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Icon name="external" size={15} />
              Open original
            </a>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => describeMutation.mutate({ mediaId: media.media_id })}
              disabled={describePending || deletePending || confirmingDelete}
              aria-busy={describePending}
            >
              <Icon name="spark" size={15} />
              {describePending ? "Re-describing…" : "Re-describe with AI"}
            </Button>
            {confirmingDelete ? null : (
              <Button
                id={deleteActionId}
                variant="ghost"
                size="sm"
                className="media-detail__delete"
                onClick={() => setConfirmingDelete(true)}
                disabled={describePending || deletePending}
              >
                <Icon name="close" size={15} />
                Delete
              </Button>
            )}
          </div>

          {describeError ? (
            <div className="media-detail__error" role="alert">
              <Icon name="info" size={16} />
              <div>
                <p>{mediaErrorMessage(describeError)}</p>
                {isProviderUnavailable(describeError) ? (
                  <p className="media-detail__provider">
                    A vision-capable chat provider is required for AI captions and OCR. Configure
                    one in <Link to="/settings">Settings</Link>, then run Re-describe with AI
                    again.
                  </p>
                ) : null}
                {isCaptionFailure(describeError) ? (
                  <p className="media-detail__provider">
                    The configured vision provider rejected the request. Check its model and API
                    key in <Link to="/settings">Settings</Link>.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          {confirmingDelete ? (
            <div
              ref={confirmRef}
              className="media-detail__confirm"
              role="group"
              aria-labelledby={deleteHeadingId}
              tabIndex={-1}
            >
              <p className="eyebrow" id={deleteHeadingId}>
                Confirm deletion
              </p>
              <p>
                Delete “{title}” from the media index? It will disappear from the sheets, text
                search, and visual similarity. This cannot be undone.
              </p>
              <div className="media-detail__confirm-actions">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirmingDelete(false)}
                  disabled={deletePending}
                >
                  Keep image
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  className="media-delete-confirm"
                  onClick={() => deleteMutation.mutate({ mediaId: media.media_id })}
                  disabled={deletePending}
                  aria-busy={deletePending}
                >
                  {deletePending ? "Deleting…" : "Delete image"}
                  {deletePending ? null : <Icon name="close" size={15} />}
                </Button>
              </div>
              {deleteError ? (
                <p className="media-detail__delete-error" role="alert">
                  <Icon name="info" size={15} />
                  <span>{mediaErrorMessage(deleteError)}</span>
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </MediaDialog>
  );
}
