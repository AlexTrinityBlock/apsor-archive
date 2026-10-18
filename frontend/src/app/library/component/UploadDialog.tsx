import { useId, useState, type ChangeEvent, type FormEvent } from "react";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useCreateTextFile, useUploadFile } from "../../generated-apis-types/files/files";
import { formatBytes, formatNumber } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { LibraryDialog } from "./LibraryDialog";
import {
  ACCEPTED_FILE_TYPES,
  MAX_TEXT_BYTES,
  MAX_UPLOAD_BYTES,
  describeError,
  hasFileName,
  isAcceptedFileName,
  normalizeArchivePath,
  textByteLength,
} from "./library-utils";

type IntakeTab = "upload" | "text";

interface UploadDialogProps {
  readonly currentPath: string;
  readonly onClose: () => void;
  readonly onUploaded: (file: FileSchema) => void;
}

function pathPrefix(path: string): string {
  const normalized = normalizeArchivePath(path);
  return normalized === "" || normalized === "/" ? "/" : `${normalized}/`;
}

function FormError({ message }: { readonly message: string }) {
  return (
    <p className="library-form__error" role="alert">
      <Icon name="info" size={15} />
      <span>{message}</span>
    </p>
  );
}

/**
 * The intake desk: one modal with an upload tab and a plain-text tab. Both
 * mutations return the new file so the page can open its reader immediately.
 */
export function UploadDialog({ currentPath, onClose, onUploaded }: UploadDialogProps) {
  const baseId = useId();
  const uploadPathId = `${baseId}-upload-path`;
  const uploadFileId = `${baseId}-upload-file`;
  const textPathId = `${baseId}-text-path`;
  const textContentId = `${baseId}-text-content`;
  const uploadTabId = `${baseId}-upload-tab`;
  const textTabId = `${baseId}-text-tab`;
  const uploadPanelId = `${baseId}-upload-panel`;
  const textPanelId = `${baseId}-text-panel`;

  const [tab, setTab] = useState<IntakeTab>("upload");
  const [uploadPath, setUploadPath] = useState(() => pathPrefix(currentPath));
  const [textPath, setTextPath] = useState(() => pathPrefix(currentPath));
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [textContent, setTextContent] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const uploadMutation = useUploadFile({
    mutation: {
      onSuccess: (file) => onUploaded(file),
    },
  });
  const textMutation = useCreateTextFile({
    mutation: {
      onSuccess: (file) => onUploaded(file),
    },
  });

  const textBytes = textByteLength(textContent);
  const uploadPending = uploadMutation.isPending;
  const textPending = textMutation.isPending;

  const selectTab = (next: IntakeTab) => {
    setTab(next);
    setLocalError(null);
    uploadMutation.reset();
    textMutation.reset();
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setLocalError(null);
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (!isAcceptedFileName(file.name)) {
      setSelectedFile(null);
      event.target.value = "";
      setLocalError("Choose a Markdown, text, CSV, JSON, log, or PDF file.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setSelectedFile(null);
      event.target.value = "";
      setLocalError("This file is larger than the 10 MB upload limit.");
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    const path = normalizeArchivePath(uploadPath);
    if (!hasFileName(path)) {
      setLocalError("Enter the full archive path, including the file name.");
      return;
    }
    if (!selectedFile) {
      setLocalError("Choose a file to upload.");
      return;
    }
    uploadMutation.mutate({ data: { path, file: selectedFile } });
  };

  const handleCreateText = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    const path = normalizeArchivePath(textPath);
    if (!hasFileName(path)) {
      setLocalError("Enter the full archive path, including the file name.");
      return;
    }
    if (textContent.trim().length === 0) {
      setLocalError("Write some content before creating the file.");
      return;
    }
    if (textBytes > MAX_TEXT_BYTES) {
      setLocalError("This text is larger than the 2 MB creation limit.");
      return;
    }
    textMutation.mutate({ data: { path, content: textContent } });
  };

  const uploadError = uploadMutation.error ? describeError(uploadMutation.error) : null;
  const textError = textMutation.error ? describeError(textMutation.error) : null;

  return (
    <LibraryDialog
      eyebrow="Intake desk"
      title="Add a file to the archive"
      description="A path becomes a leaf. Re-uploading the same path creates a new version and keeps the old one in history."
      onClose={onClose}
      dismissible={!uploadPending && !textPending}
      className="library-intake"
    >
      <div className="library-tabs" role="tablist" aria-label="Intake method">
        <button
          type="button"
          role="tab"
          id={uploadTabId}
          aria-selected={tab === "upload"}
          aria-controls={uploadPanelId}
          className={tab === "upload" ? "library-tab is-active" : "library-tab"}
          onClick={() => selectTab("upload")}
          disabled={uploadPending || textPending}
        >
          <Icon name="arrow-down" size={15} />
          Upload file
        </button>
        <button
          type="button"
          role="tab"
          id={textTabId}
          aria-selected={tab === "text"}
          aria-controls={textPanelId}
          className={tab === "text" ? "library-tab is-active" : "library-tab"}
          onClick={() => selectTab("text")}
          disabled={uploadPending || textPending}
        >
          <Icon name="file" size={15} />
          New text file
        </button>
      </div>

      {tab === "upload" ? (
        <div role="tabpanel" id={uploadPanelId} aria-labelledby={uploadTabId}>
          <form className="library-form" onSubmit={handleUpload}>
            <label className="library-field" htmlFor={uploadPathId}>
              <span className="library-field__label">Archive path</span>
              <input
                id={uploadPathId}
                className="library-input"
                type="text"
                value={uploadPath}
                onChange={(event) => setUploadPath(event.target.value)}
                placeholder="/notes/field-notes.md"
                autoComplete="off"
                spellCheck={false}
                data-autofocus
              />
              <span className="library-field__hint">
                Full path, including the file name. Missing folders are created.
              </span>
            </label>

            <label className="library-field" htmlFor={uploadFileId}>
              <span className="library-field__label">File</span>
              <input
                id={uploadFileId}
                className="library-input library-input--file"
                type="file"
                accept={ACCEPTED_FILE_TYPES}
                onChange={handleFileChange}
              />
              <span className="library-field__hint">
                One file · up to 10 MB · .md, .txt, .csv, .json, .log, .pdf,
                .docx, .jpg, .jpeg, .png, .webp
              </span>
            </label>

            {selectedFile ? (
              <div className="library-file-chip">
                <Icon name="file" size={16} />
                <span className="library-file-chip__name">{selectedFile.name}</span>
                <span className="library-file-chip__size">{formatBytes(selectedFile.size)}</span>
              </div>
            ) : null}

            {localError ? <FormError message={localError} /> : null}
            {uploadError ? <FormError message={uploadError} /> : null}

            <div className="library-form__actions">
              <Button variant="ghost" size="sm" onClick={onClose} disabled={uploadPending}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm" disabled={uploadPending}>
                {uploadPending ? "Uploading…" : "Upload file"}
                <Icon name="arrow-down" size={15} />
              </Button>
            </div>
          </form>
        </div>
      ) : (
        <div role="tabpanel" id={textPanelId} aria-labelledby={textTabId}>
          <form className="library-form" onSubmit={handleCreateText}>
            <label className="library-field" htmlFor={textPathId}>
              <span className="library-field__label">Archive path</span>
              <input
                id={textPathId}
                className="library-input"
                type="text"
                value={textPath}
                onChange={(event) => setTextPath(event.target.value)}
                placeholder="/notes/reading-list.md"
                autoComplete="off"
                spellCheck={false}
                data-autofocus
              />
              <span className="library-field__hint">
                Full path, including the file name. Missing folders are created.
              </span>
            </label>

            <label className="library-field" htmlFor={textContentId}>
              <span className="library-field__label">Content</span>
              <textarea
                id={textContentId}
                className="library-textarea"
                value={textContent}
                onChange={(event) => setTextContent(event.target.value)}
                placeholder="# Reading list&#10;&#10;A note written straight into the archive."
                rows={10}
                spellCheck={false}
                aria-invalid={textBytes > MAX_TEXT_BYTES}
              />
              <span className="library-field__hint">
                Plain UTF-8 text · up to 2 MB · {formatNumber(textContent.length)} characters ·{" "}
                {formatBytes(textBytes)}
              </span>
            </label>

            {localError ? <FormError message={localError} /> : null}
            {textError ? <FormError message={textError} /> : null}

            <div className="library-form__actions">
              <Button variant="ghost" size="sm" onClick={onClose} disabled={textPending}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm" disabled={textPending}>
                {textPending ? "Creating…" : "Create text file"}
                <Icon name="plus" size={15} />
              </Button>
            </div>
          </form>
        </div>
      )}
    </LibraryDialog>
  );
}
