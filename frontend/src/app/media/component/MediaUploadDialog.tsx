import { useId, useState, type ChangeEvent, type FormEvent } from "react";

import type { BodyUploadMedia, MediaSchema } from "../../generated-apis-types/schemas";
import { useUploadMedia } from "../../generated-apis-types/media/media";
import { formatBytes } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { MediaDialog } from "./MediaDialog";
import {
  MAX_MEDIA_BYTES,
  MEDIA_ACCEPT,
  isSupportedMediaFile,
  mediaErrorMessage,
  normalizeMediaTags,
  normalizeMediaUploadPath,
  validateMediaUploadPath,
} from "./media-utils";

interface MediaUploadDialogProps {
  readonly onClose: () => void;
  readonly onUploaded: (media: MediaSchema) => void;
}

function FormError({ message }: { readonly message: string }) {
  return (
    <p className="media-form__error" role="alert">
      <Icon name="info" size={15} />
      <span>{message}</span>
    </p>
  );
}

/**
 * Intake for the standalone visual index. Path, caption, and tags are all
 * optional; captions and tags can be generated when a vision provider exists.
 */
export function MediaUploadDialog({ onClose, onUploaded }: MediaUploadDialogProps) {
  const baseId = useId();
  const fileId = `${baseId}-file`;
  const pathId = `${baseId}-path`;
  const captionId = `${baseId}-caption`;
  const tagsId = `${baseId}-tags`;

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [path, setPath] = useState("");
  const [caption, setCaption] = useState("");
  const [tags, setTags] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const uploadMutation = useUploadMedia({
    mutation: {
      onSuccess: (media) => onUploaded(media),
    },
  });

  const pending = uploadMutation.isPending;
  const uploadError = uploadMutation.error ? mediaErrorMessage(uploadMutation.error) : null;

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setLocalError(null);
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (!isSupportedMediaFile(file)) {
      setSelectedFile(null);
      event.target.value = "";
      setLocalError("Choose a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > MAX_MEDIA_BYTES) {
      setSelectedFile(null);
      event.target.value = "";
      setLocalError("This image is larger than the 10 MB upload limit.");
      return;
    }
    setSelectedFile(file);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);

    const normalizedPath = normalizeMediaUploadPath(path);
    const pathProblem = validateMediaUploadPath(normalizedPath);
    if (pathProblem) {
      setLocalError(pathProblem);
      return;
    }
    if (!selectedFile) {
      setLocalError("Choose an image to add to the archive.");
      return;
    }

    const data: BodyUploadMedia = { file: selectedFile };
    if (normalizedPath) {
      data.path = normalizedPath;
    }
    if (caption.trim().length > 0) {
      data.caption = caption.trim();
    }
    const normalizedTags = normalizeMediaTags(tags);
    if (normalizedTags) {
      data.tags = normalizedTags;
    }

    uploadMutation.mutate({ data });
  };

  return (
    <MediaDialog
      eyebrow="Image intake"
      title="Add an image to the visual archive"
      description="One JPEG, PNG, or WebP. The server reads dimensions and visual features; a vision-capable provider can also write the caption, OCR text, title, summary, tags, and document type."
      onClose={onClose}
      dismissible={!pending}
      className="media-upload-dialog"
    >
      <form className="media-form" onSubmit={handleSubmit}>
        <label className="media-field" htmlFor={fileId}>
          <span className="media-field__label">Image</span>
          <input
            id={fileId}
            className="media-input media-input--file"
            type="file"
            accept={MEDIA_ACCEPT}
            onChange={handleFileChange}
            data-autofocus
          />
          <span className="media-field__hint">
            JPEG, PNG, or WebP · up to 10 MB · one image per intake
          </span>
        </label>

        {selectedFile ? (
          <div className="media-file-chip">
            <Icon name="ring" size={16} />
            <span className="media-file-chip__name">{selectedFile.name}</span>
            <span className="media-file-chip__size">{formatBytes(selectedFile.size)}</span>
          </div>
        ) : null}

        <label className="media-field" htmlFor={pathId}>
          <span className="media-field__label">Full path · optional</span>
          <input
            id={pathId}
            className="media-input"
            type="text"
            value={path}
            onChange={(event) => {
              setPath(event.target.value);
              setLocalError(null);
            }}
            placeholder="/media/benz.jpg"
            autoComplete="off"
            spellCheck={false}
          />
          <span className="media-field__hint">
            Include the file name. Leave blank and the server stores the image under /media with a
            generated name.
          </span>
        </label>

        <label className="media-field" htmlFor={captionId}>
          <span className="media-field__label">Caption · optional</span>
          <textarea
            id={captionId}
            className="media-textarea"
            value={caption}
            onChange={(event) => setCaption(event.target.value)}
            placeholder="Describe what the image shows…"
            rows={4}
            spellCheck
          />
          <span className="media-field__hint">
            A supplied caption is indexed exactly as written. Leave it blank to let the vision
            provider describe the image.
          </span>
        </label>

        <label className="media-field" htmlFor={tagsId}>
          <span className="media-field__label">Tags · optional</span>
          <input
            id={tagsId}
            className="media-input"
            type="text"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="vintage, motor vehicle, black and white"
            autoComplete="off"
            spellCheck={false}
          />
          <span className="media-field__hint">Comma-separated. Duplicates are removed.</span>
        </label>

        <p className="media-form__note">
          <Icon name="spark" size={15} />
          <span>
            When the caption is blank and a vision-capable chat provider is configured, the
            server generates the caption, OCR text, title, summary, tags, and document type.
          </span>
        </p>

        {localError ? <FormError message={localError} /> : null}
        {uploadError ? <FormError message={uploadError} /> : null}

        <div className="media-form__actions">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={pending} aria-busy={pending}>
            {pending ? "Reading the image…" : "Add image"}
            {pending ? null : <Icon name="plus" size={15} />}
          </Button>
        </div>
      </form>
    </MediaDialog>
  );
}
