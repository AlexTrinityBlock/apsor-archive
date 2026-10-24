import {
  useId,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

import type { FileSchema, IngestJobSchema } from "../../generated-apis-types/schemas";
import {
  useCreateTextFileAsync,
  useRetryIngestJob,
  useUploadFileAsync,
} from "../../generated-apis-types/files/files";
import { formatBytes, formatNumber } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { IngestProgress } from "./IngestProgress";
import { LibraryDialog } from "./LibraryDialog";
import {
  ACCEPTED_FILE_TYPES,
  MAX_TEXT_BYTES,
  MAX_UPLOAD_BYTES,
  hasFileName,
  isAcceptedFileName,
  normalizeArchivePath,
  textByteLength,
} from "./library-utils";
import {
  useIngestRun,
  type IngestRunFailure,
  type IngestRunPhase,
} from "../hook/useIngestRun";

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

/**
 * Grows a folder-shaped path with the picked file's name.
 *
 * The dialog starts with the current folder (for example `/檔案A/`), and the
 * server reads the final path segment as the file name, so leaving it as a
 * folder fails with a missing-extension error. A path that already names a
 * supported file wins, so renaming on upload still works, while a name this
 * handler filled in earlier is replaced when another file is picked.
 */
function pathWithFileName(
  path: string,
  fileName: string,
  previousFileName: string | null,
): string {
  const trimmed = path.trim();
  const folder = normalizeArchivePath(trimmed);
  const segments = folder.split("/").filter(Boolean);
  const lastSegment = segments[segments.length - 1] ?? "";

  if (previousFileName !== null && lastSegment === previousFileName) {
    segments[segments.length - 1] = fileName;
    return `/${segments.join("/")}`;
  }

  const isFolderShaped =
    trimmed === "" || trimmed.endsWith("/") || !isAcceptedFileName(lastSegment);
  if (!isFolderShaped) {
    return path;
  }
  return folder === "" || folder === "/" ? `/${fileName}` : `${folder}/${fileName}`;
}

function intakeSubmitLabel(tab: IntakeTab, phase: IngestRunPhase): string {
  if (phase === "enqueueing") {
    return tab === "upload" ? "Uploading…" : "Creating…";
  }
  if (phase === "processing") {
    return "Processing…";
  }
  return tab === "upload" ? "Upload file" : "Create text file";
}

function enqueueProgressLabel(
  tab: IntakeTab,
  phase: IngestRunPhase,
): string | undefined {
  if (phase !== "enqueueing") {
    return undefined;
  }
  return tab === "upload" ? "Uploading" : "Queuing";
}

function FormError({ message }: { readonly message: string }) {
  return (
    <p className="library-form__error" role="alert">
      <Icon name="info" size={15} />
      <span>{message}</span>
    </p>
  );
}

function IntakeMessages({
  localError,
  failure,
}: {
  readonly localError: string | null;
  readonly failure: IngestRunFailure | null;
}) {
  if (!localError && !failure) {
    return null;
  }
  return (
    <>
      {localError ? <FormError message={localError} /> : null}
      {failure ? <FormError message={failure.message} /> : null}
    </>
  );
}

function IntakeActions({
  busy,
  submitLabel,
  submitIcon,
  canRetry,
  onCancel,
  onRetry,
}: {
  readonly busy: boolean;
  readonly submitLabel: string;
  readonly submitIcon: "plus" | "arrow-down";
  readonly canRetry: boolean;
  readonly onCancel: () => void;
  readonly onRetry: () => void;
}) {
  return (
    <div className="library-form__actions">
      <Button variant="ghost" size="sm" onClick={onCancel}>
        {busy ? "Stop waiting" : "Cancel"}
      </Button>
      {canRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} disabled={busy}>
          <Icon name="history" size={15} />
          Retry ingest
        </Button>
      ) : null}
      <Button type="submit" variant="primary" size="sm" disabled={busy}>
        {submitLabel}
        <Icon name={submitIcon} size={15} />
      </Button>
    </div>
  );
}

interface ProgressPanelProps {
  readonly tab: IntakeTab;
  readonly phase: IngestRunPhase;
  readonly job: IngestJobSchema | null;
  readonly selectedFile: File | null;
  readonly uploadPath: string;
  readonly textPath: string;
}

function IntakeProgressPanel({
  tab,
  phase,
  job,
  selectedFile,
  uploadPath,
  textPath,
}: ProgressPanelProps) {
  if (job === null && phase === "idle") {
    return null;
  }

  const activePath = normalizeArchivePath(tab === "upload" ? uploadPath : textPath);
  const fileNameFromPath = activePath.split("/").filter(Boolean).pop() ?? "New file";
  const progressName =
    job?.file_name ?? (tab === "upload" ? selectedFile?.name : null) ?? fileNameFromPath;
  const progressPath = job?.path ?? (activePath || "/");
  const progressLabel = enqueueProgressLabel(tab, phase);

  return (
    <section className="library-intake__progress" aria-label="Ingestion progress">
      <div className="library-intake__progress-file">
        <Icon name="file" size={15} />
        <span className="library-intake__progress-name">{progressName}</span>
        {job ? <span className="library-intake__progress-job">Job #{job.id}</span> : null}
      </div>
      <code className="library-intake__progress-path">{progressPath}</code>
      <IngestProgress
        variant="large"
        stage={job?.status ?? null}
        progressPct={job?.progress_pct ?? null}
        chunksTotal={job?.chunks_total ?? null}
        chunksEmbedded={job?.chunks_embedded ?? null}
        label={progressLabel}
      />
      {phase === "idle" ? null : (
        <p className="library-intake__progress-note">
          Closing this dialog stops the progress view only; the durable job keeps running.
        </p>
      )}
    </section>
  );
}

interface UploadTabPanelProps {
  readonly uploadPathId: string;
  readonly uploadFileId: string;
  readonly uploadTabId: string;
  readonly uploadPanelId: string;
  readonly uploadPath: string;
  readonly selectedFile: File | null;
  readonly busy: boolean;
  readonly progress: ProgressPanelProps;
  readonly localError: string | null;
  readonly failure: IngestRunFailure | null;
  readonly canRetry: boolean;
  readonly submitLabel: string;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly onPathChange: (value: string) => void;
  readonly onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  readonly onCancel: () => void;
  readonly onRetry: () => void;
}

function UploadTabPanel({
  uploadPathId,
  uploadFileId,
  uploadTabId,
  uploadPanelId,
  uploadPath,
  selectedFile,
  busy,
  progress,
  localError,
  failure,
  canRetry,
  submitLabel,
  onSubmit,
  onPathChange,
  onFileChange,
  onCancel,
  onRetry,
}: UploadTabPanelProps) {
  return (
    <div role="tabpanel" id={uploadPanelId} aria-labelledby={uploadTabId}>
      <form className="library-form" onSubmit={onSubmit}>
        <label className="library-field" htmlFor={uploadPathId}>
          <span className="library-field__label">Archive path</span>
          <input
            id={uploadPathId}
            className="library-input"
            type="text"
            value={uploadPath}
            onChange={(event) => onPathChange(event.target.value)}
            placeholder="/notes/field-notes.md"
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
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
            onChange={onFileChange}
            disabled={busy}
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

        <IntakeProgressPanel {...progress} />
        <IntakeMessages localError={localError} failure={failure} />
        <IntakeActions
          busy={busy}
          submitLabel={submitLabel}
          submitIcon="arrow-down"
          canRetry={canRetry}
          onCancel={onCancel}
          onRetry={onRetry}
        />
      </form>
    </div>
  );
}

interface TextTabPanelProps {
  readonly textPathId: string;
  readonly textContentId: string;
  readonly textTabId: string;
  readonly textPanelId: string;
  readonly textPath: string;
  readonly textContent: string;
  readonly textBytes: number;
  readonly busy: boolean;
  readonly progress: ProgressPanelProps;
  readonly localError: string | null;
  readonly failure: IngestRunFailure | null;
  readonly canRetry: boolean;
  readonly submitLabel: string;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly onPathChange: (value: string) => void;
  readonly onContentChange: (value: string) => void;
  readonly onCancel: () => void;
  readonly onRetry: () => void;
}

function TextTabPanel({
  textPathId,
  textContentId,
  textTabId,
  textPanelId,
  textPath,
  textContent,
  textBytes,
  busy,
  progress,
  localError,
  failure,
  canRetry,
  submitLabel,
  onSubmit,
  onPathChange,
  onContentChange,
  onCancel,
  onRetry,
}: TextTabPanelProps) {
  return (
    <div role="tabpanel" id={textPanelId} aria-labelledby={textTabId}>
      <form className="library-form" onSubmit={onSubmit}>
        <label className="library-field" htmlFor={textPathId}>
          <span className="library-field__label">Archive path</span>
          <input
            id={textPathId}
            className="library-input"
            type="text"
            value={textPath}
            onChange={(event) => onPathChange(event.target.value)}
            placeholder="/notes/reading-list.md"
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
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
            onChange={(event) => onContentChange(event.target.value)}
            placeholder="# Reading list&#10;&#10;A note written straight into the archive."
            rows={10}
            spellCheck={false}
            aria-invalid={textBytes > MAX_TEXT_BYTES}
            disabled={busy}
          />
          <span className="library-field__hint">
            Plain UTF-8 text · up to 2 MB · {formatNumber(textContent.length)} characters ·{" "}
            {formatBytes(textBytes)}
          </span>
        </label>

        <IntakeProgressPanel {...progress} />
        <IntakeMessages localError={localError} failure={failure} />
        <IntakeActions
          busy={busy}
          submitLabel={submitLabel}
          submitIcon="plus"
          canRetry={canRetry}
          onCancel={onCancel}
          onRetry={onRetry}
        />
      </form>
    </div>
  );
}

/**
 * The intake desk: one modal with an upload tab and a plain-text tab. Both
 * async endpoints return a durable job immediately; the dialog then follows
 * that job's stage and progress until the published file can be opened.
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

  const uploadMutation = useUploadFileAsync();
  const textMutation = useCreateTextFileAsync();
  const retryMutation = useRetryIngestJob();
  const run = useIngestRun(onUploaded);

  const textBytes = textByteLength(textContent);
  const busy = run.phase !== "idle";
  const canRetry = typeof run.failure?.retryJobId === "number";
  const submitLabel = intakeSubmitLabel(tab, run.phase);
  const progress: ProgressPanelProps = {
    tab,
    phase: run.phase,
    job: run.job,
    selectedFile,
    uploadPath,
    textPath,
  };

  const selectTab = (next: IntakeTab) => {
    setTab(next);
    setLocalError(null);
    run.reset();
    uploadMutation.reset();
    textMutation.reset();
    retryMutation.reset();
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setLocalError(null);
    const previousFileName = selectedFile?.name ?? null;
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
    setUploadPath((current) => pathWithFileName(current, file.name, previousFileName));
  };

  const handleUpload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) {
      return;
    }
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
    run.start(() => uploadMutation.mutateAsync({ data: { path, file: selectedFile } }));
  };

  const handleCreateText = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) {
      return;
    }
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
    run.start(() => textMutation.mutateAsync({ data: { path, content: textContent } }));
  };

  const handleRetry = () => {
    const jobId = run.failure?.retryJobId;
    if (typeof jobId !== "number" || busy) {
      return;
    }
    run.start(() => retryMutation.mutateAsync({ jobId }));
  };

  const handleCancel = () => {
    if (busy) {
      run.cancel();
    }
    onClose();
  };

  return (
    <LibraryDialog
      eyebrow="Intake desk"
      title="Add a file to the archive"
      description="A path becomes a leaf. Re-uploading the same path creates a new version and keeps the old one in history."
      onClose={onClose}
      dismissible={!busy}
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
          disabled={busy}
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
          disabled={busy}
        >
          <Icon name="file" size={15} />
          New text file
        </button>
      </div>

      {tab === "upload" ? (
        <UploadTabPanel
          uploadPathId={uploadPathId}
          uploadFileId={uploadFileId}
          uploadTabId={uploadTabId}
          uploadPanelId={uploadPanelId}
          uploadPath={uploadPath}
          selectedFile={selectedFile}
          busy={busy}
          progress={progress}
          localError={localError}
          failure={run.failure}
          canRetry={canRetry}
          submitLabel={submitLabel}
          onSubmit={handleUpload}
          onPathChange={setUploadPath}
          onFileChange={handleFileChange}
          onCancel={handleCancel}
          onRetry={handleRetry}
        />
      ) : (
        <TextTabPanel
          textPathId={textPathId}
          textContentId={textContentId}
          textTabId={textTabId}
          textPanelId={textPanelId}
          textPath={textPath}
          textContent={textContent}
          textBytes={textBytes}
          busy={busy}
          progress={progress}
          localError={localError}
          failure={run.failure}
          canRetry={canRetry}
          submitLabel={submitLabel}
          onSubmit={handleCreateText}
          onPathChange={setTextPath}
          onContentChange={setTextContent}
          onCancel={handleCancel}
          onRetry={handleRetry}
        />
      )}
    </LibraryDialog>
  );
}
