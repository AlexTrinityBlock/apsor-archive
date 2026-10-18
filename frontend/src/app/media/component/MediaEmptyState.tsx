import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";

interface MediaEmptyArchiveProps {
  readonly onAddImage: () => void;
}

interface MediaNoResultsProps {
  readonly mode: "text" | "visual";
  readonly query?: string;
  readonly onClear: () => void;
  readonly onAddImage: () => void;
}

/**
 * First-run intake sheet. It looks like a dropzone but keeps the action
 * explicit: the upload dialog owns file selection and validation.
 */
export function MediaEmptyArchive({ onAddImage }: MediaEmptyArchiveProps) {
  return (
    <section className="media-empty reveal reveal-3" aria-labelledby="media-empty-title">
      <div className="media-empty__frame" aria-hidden="true" />
      <div className="media-empty__stamp" aria-hidden="true">
        Image intake · Vol. 01
      </div>
      <div className="media-empty__icon" aria-hidden="true">
        <Icon name="ring" size={34} />
      </div>
      <p className="eyebrow">Standalone media index</p>
      <h2 id="media-empty-title">The visual archive is waiting for its first image.</h2>
      <p className="media-empty__description">
        Add a JPEG, PNG, or WebP image. When a vision-capable provider is configured, it writes
        the caption and reads OCR text; the server also records a visual fingerprint so the image
        can be found by another image. Media is indexed on its own and never mixed into the file
        library&apos;s text chunks.
      </p>

      <ul className="media-empty__process">
        <li>
          <span className="media-empty__step">01</span>
          <span>
            <strong>Caption</strong>
            <small>A description becomes searchable text.</small>
          </span>
        </li>
        <li>
          <span className="media-empty__step">02</span>
          <span>
            <strong>OCR</strong>
            <small>Printed text inside the image is preserved.</small>
          </span>
        </li>
        <li>
          <span className="media-empty__step">03</span>
          <span>
            <strong>Visual fingerprint</strong>
            <small>Image-to-image search compares the pictures themselves.</small>
          </span>
        </li>
      </ul>

      <div className="media-empty__actions">
        <Button variant="primary" size="md" onClick={onAddImage}>
          <Icon name="plus" size={16} />
          Add image
        </Button>
        <Badge tone="neutral">No text chunks involved</Badge>
      </div>

      <div className="endpoint-label">
        <span>POST</span>
        <code>/api/v1/media</code>
      </div>
    </section>
  );
}

/** A quiet zero-result sheet for either text search or visual search. */
export function MediaNoResults({ mode, query, onClear, onAddImage }: MediaNoResultsProps) {
  const isVisual = mode === "visual";

  return (
    <EmptyState
      icon={isVisual ? "ring" : "search"}
      eyebrow={isVisual ? "Image to image · no neighbours" : "Text to image · no matches"}
      title={
        isVisual
          ? "No visual neighbours yet."
          : `No images match “${query ?? ""}”.`
      }
      description={
        isVisual
          ? "This image is not close to anything in the visual index yet. Add another image to give the fingerprint space to work, or clear the query image and browse the sheets."
          : "Try a broader word, a tag, or a phrase that may appear in a caption or OCR text. Media search only reads the standalone visual index."
      }
      endpoint={isVisual ? "/api/v1/media/search/image" : "/api/v1/media/search"}
      method={isVisual ? "POST" : "GET"}
      className="media-no-results reveal reveal-3"
      action={
        <div className="empty-state__actions">
          <Button variant="secondary" size="sm" onClick={onClear}>
            {isVisual ? "Clear image search" : "Clear search"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onAddImage}>
            <Icon name="plus" size={15} />
            Add image
          </Button>
        </div>
      }
    />
  );
}
