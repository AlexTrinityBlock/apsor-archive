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
} from "../../generated-apis-types/files/files";
import { formatBytes } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n, type Translate } from "../../i18n";
import { IngestProgress } from "./IngestProgress";
import { LibraryDialog } from "./LibraryDialog";
import {
  ACCEPTED_FILE_TYPES,
  MAX_TEXT_BYTES,
  MAX_UPLOAD_BYTES,
  isAcceptedFileName,
  isSafeUploadName,
  joinArchivePath,
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
  readonly onUploadFiles: (files: readonly File[]) => void;
  readonly onUploaded: (file: FileSchema) => void;
}

/** The upload destination is the folder the dialog was opened from, never a
 * user-typed path. */
function fixedFolder(path: string): string {
  const normalized = normalizeArchivePath(path);
  return normalized.length === 0 ? "/" : normalized;
}

/** Text creation uses the same fixed folder; only the leaf name is editable. */
function ensureTextFileName(rawName: string): string {
  const name = rawName.trim();
  if (name.length === 0) {
    return "";
  }
  const lower = name.toLowerCase();
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) {
    return name;
  }
  return `${name}.md`;
}

/** Control characters (C0, DEL, and C1) must not appear in a file name. */
function hasControlCharacter(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint < 0x20 || (codePoint >= 0x7f && codePoint <= 0x9f)) {
      return true;
    }
  }
  return false;
}

/** Allow a single leaf name only: no separators, no traversal, no controls. */
function isSafeTextFileName(name: string): boolean {
  return (
    isSafeUploadName(name) &&
    name.length <= 255 &&
    !hasControlCharacter(name)
  );
}

/** Merge a new picker selection into the current list without duplicate names. */
function mergeFiles(current: readonly File[], incoming: readonly File[]): File[] {
  const byName = new Map(current.map((file) => [file.name, file] as const));
  for (const file of incoming) {
    byName.set(file.name, file);
  }
  return [...byName.values()];
}

function textSubmitLabel(t: Translate, phase: IngestRunPhase): string {
  if (phase === "enqueueing") {
    return t("library.upload.creating");
  }
  if (phase === "processing") {
    return t("library.upload.processing");
  }
  return t("library.upload.submitText");
}

function enqueueProgressLabel(
  t: Translate,
  phase: IngestRunPhase,
): string | undefined {
  return phase === "enqueueing" ? t("library.upload.queuing") : undefined;
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

function FixedFolderField({
  label,
  hint,
  path,
}: {
  readonly label: string;
  readonly hint: string;
  readonly path: string;
}) {
  return (
    <div className="library-field">
      <span className="library-field__label">{label}</span>
      <code className="library-fixed-path" data-page-context="exclude">
        {path}
      </code>
      <span className="library-field__hint">{hint}</span>
    </div>
  );
}

interface ProgressPanelProps {
  readonly phase: IngestRunPhase;
  readonly job: IngestJobSchema | null;
  readonly path: string;
}

function IntakeProgressPanel({ phase, job, path }: ProgressPanelProps) {
  const { t } = useI18n();
  if (job === null && phase === "idle") {
    return null;
  }

  const fileNameFromPath =
    path.split("/").filter(Boolean).pop() ?? t("library.upload.newFileFallback");
  const progressName = job?.file_name ?? fileNameFromPath;
  const progressPath = job?.path ?? (path || "/");
  const progressLabel = enqueueProgressLabel(t, phase);

  return (
    <section
      className="library-intake__progress"
      aria-label={t("library.ingest.progressAria")}
    >
      <div className="library-intake__progress-file">
        <Icon name="file" size={15} />
        <span className="library-intake__progress-name">{progressName}</span>
        {job ? (
          <span className="library-intake__progress-job">
            {t("library.ingest.jobId", { id: job.id })}
          </span>
        ) : null}
      </div>
      <code className="library-intake__progress-path">{progressPath}</code>
      <IngestProgress
        variant="large"
        stage={job?.status ?? null}
        progressPct={job?.progress_pct ?? null}
        stageDone={job?.stage_done ?? null}
        stageTotal={job?.stage_total ?? null}
        stageUnit={job?.stage_unit ?? null}
        chunksTotal={job?.chunks_total ?? null}
        chunksEmbedded={job?.chunks_embedded ?? null}
        label={progressLabel}
      />
      {phase === "idle" ? null : (
        <p className="library-intake__progress-note">
          {t("library.upload.closeNote")}
        </p>
      )}
    </section>
  );
}

interface UploadTabPanelProps {
  readonly uploadFileId: string;
  readonly uploadTabId: string;
  readonly uploadPanelId: string;
  readonly destination: string;
  readonly selectedFiles: readonly File[];
  readonly localError: string | null;
  readonly submitLabel: string;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  readonly onRemoveFile: (name: string) => void;
  readonly onCancel: () => void;
}

function UploadTabPanel({
  uploadFileId,
  uploadTabId,
  uploadPanelId,
  destination,
  selectedFiles,
  localError,
  submitLabel,
  onSubmit,
  onFileChange,
  onRemoveFile,
  onCancel,
}: UploadTabPanelProps) {
  const { t } = useI18n();
  return (
    <div role="tabpanel" id={uploadPanelId} aria-labelledby={uploadTabId}>
      <form className="library-form" onSubmit={onSubmit}>
        <FixedFolderField
          label={t("library.upload.destinationLabel")}
          hint={t("library.upload.destinationHint")}
          path={destination}
        />

        <label className="library-field" htmlFor={uploadFileId}>
          <span className="library-field__label">{t("library.upload.fileLabel")}</span>
          <input
            id={uploadFileId}
            className="library-input library-input--file"
            type="file"
            accept={ACCEPTED_FILE_TYPES}
            multiple
            onChange={onFileChange}
            data-autofocus
          />
          <span className="library-field__hint">
            {t("library.upload.fileHint")}
          </span>
        </label>

        {selectedFiles.length > 0 ? (
          <ul
            className="library-file-list"
            aria-label={t("library.upload.selectedAria")}
          >
            {selectedFiles.map((file) => (
              <li className="library-file-chip" key={file.name}>
                <Icon name="file" size={16} />
                <span className="library-file-chip__name">{file.name}</span>
                <span className="library-file-chip__size">
                  {formatBytes(file.size)}
                </span>
                <button
                  type="button"
                  className="library-file-chip__remove"
                  onClick={() => onRemoveFile(file.name)}
                  aria-label={t("library.upload.removeFile", { name: file.name })}
                >
                  <Icon name="close" size={13} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <p className="library-field__hint">{t("library.upload.queueNote")}</p>
        {localError ? <FormError message={localError} /> : null}

        <div className="library-form__actions">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t("library.common.cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={selectedFiles.length === 0}
          >
            {submitLabel}
            <Icon name="arrow-up" size={15} />
          </Button>
        </div>
      </form>
    </div>
  );
}

interface TextTabPanelProps {
  readonly textFileNameId: string;
  readonly textContentId: string;
  readonly textTabId: string;
  readonly textPanelId: string;
  readonly destination: string;
  readonly textFileName: string;
  readonly textContent: string;
  readonly textBytes: number;
  readonly busy: boolean;
  readonly path: string;
  readonly phase: IngestRunPhase;
  readonly job: IngestJobSchema | null;
  readonly localError: string | null;
  readonly failure: IngestRunFailure | null;
  readonly canRetry: boolean;
  readonly submitLabel: string;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly onFileNameChange: (value: string) => void;
  readonly onContentChange: (value: string) => void;
  readonly onCancel: () => void;
  readonly onRetry: () => void;
}

function TextTabPanel({
  textFileNameId,
  textContentId,
  textTabId,
  textPanelId,
  destination,
  textFileName,
  textContent,
  textBytes,
  busy,
  path,
  phase,
  job,
  localError,
  failure,
  canRetry,
  submitLabel,
  onSubmit,
  onFileNameChange,
  onContentChange,
  onCancel,
  onRetry,
}: TextTabPanelProps) {
  const { t, formatNumber } = useI18n();
  return (
    <div role="tabpanel" id={textPanelId} aria-labelledby={textTabId}>
      <form className="library-form" onSubmit={onSubmit}>
        <FixedFolderField
          label={t("library.upload.destinationLabel")}
          hint={t("library.upload.destinationHint")}
          path={destination}
        />

        <label className="library-field" htmlFor={textFileNameId}>
          <span className="library-field__label">
            {t("library.upload.textFileNameLabel")}
          </span>
          <input
            id={textFileNameId}
            className="library-input"
            type="text"
            value={textFileName}
            onChange={(event) => onFileNameChange(event.target.value)}
            placeholder="reading-list.md"
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            data-autofocus
          />
          <span className="library-field__hint">
            {t("library.upload.textFileNameHint")}
          </span>
        </label>

        <label className="library-field" htmlFor={textContentId}>
          <span className="library-field__label">{t("library.upload.contentLabel")}</span>
          <textarea
            id={textContentId}
            className="library-textarea"
            value={textContent}
            onChange={(event) => onContentChange(event.target.value)}
            placeholder={t("library.upload.textPlaceholder")}
            rows={10}
            spellCheck={false}
            aria-invalid={textBytes > MAX_TEXT_BYTES}
            disabled={busy}
          />
          <span className="library-field__hint">
            {t("library.upload.textHint", {
              characters: formatNumber(textContent.length),
              size: formatBytes(textBytes),
            })}
          </span>
        </label>

        <IntakeProgressPanel phase={phase} job={job} path={path} />
        <IntakeMessages localError={localError} failure={failure} />
        <div className="library-form__actions">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {busy ? t("library.upload.stopWaiting") : t("library.common.cancel")}
          </Button>
          {canRetry ? (
            <Button variant="secondary" size="sm" onClick={onRetry} disabled={busy}>
              <Icon name="history" size={15} />
              {t("library.upload.retryIngest")}
            </Button>
          ) : null}
          <Button type="submit" variant="primary" size="sm" disabled={busy}>
            {submitLabel}
            <Icon name="plus" size={15} />
          </Button>
        </div>
      </form>
    </div>
  );
}

/**
 * The intake desk: one modal with a multi-file upload tab and a plain-text tab.
 * Both tabs write inside the folder the dialog was opened from; the archive
 * path is never an editable field. Uploads hand off to the page-level intake
 * queue, while text creation follows its own durable job until publishing.
 */
export function UploadDialog({
  currentPath,
  onClose,
  onUploadFiles,
  onUploaded,
}: UploadDialogProps) {
  const { t, formatNumber } = useI18n();
  const baseId = useId();
  const uploadFileId = `${baseId}-upload-file`;
  const textFileNameId = `${baseId}-text-file-name`;
  const textContentId = `${baseId}-text-content`;
  const uploadTabId = `${baseId}-upload-tab`;
  const textTabId = `${baseId}-text-tab`;
  const uploadPanelId = `${baseId}-upload-panel`;
  const textPanelId = `${baseId}-text-panel`;

  const destination = fixedFolder(currentPath);
  const [tab, setTab] = useState<IntakeTab>("upload");
  const [selectedFiles, setSelectedFiles] = useState<readonly File[]>([]);
  const [textFileName, setTextFileName] = useState("");
  const [textContent, setTextContent] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const textMutation = useCreateTextFileAsync();
  const retryMutation = useRetryIngestJob();
  const run = useIngestRun(onUploaded);

  const textBytes = textByteLength(textContent);
  const busy = run.phase !== "idle";
  const canRetry = typeof run.failure?.retryJobId === "number";
  const textFileNameValue = ensureTextFileName(textFileName);
  const textPath = joinArchivePath(destination, textFileNameValue);
  const textSubmit = textSubmitLabel(t, run.phase);
  const uploadSubmit =
    selectedFiles.length > 1
      ? t("library.upload.submitUploadOther", {
          count: formatNumber(selectedFiles.length),
        })
      : t("library.upload.submitUploadOne");

  const selectTab = (next: IntakeTab) => {
    setTab(next);
    setLocalError(null);
    run.reset();
    textMutation.reset();
    retryMutation.reset();
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length === 0) {
      return;
    }

    const accepted: File[] = [];
    const problems: string[] = [];
    for (const file of picked) {
      if (!isSafeUploadName(file.name) || !isAcceptedFileName(file.name)) {
        problems.push(t("library.upload.errorTypeName", { name: file.name }));
        continue;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        problems.push(t("library.upload.errorTooLargeName", { name: file.name }));
        continue;
      }
      accepted.push(file);
    }

    if (accepted.length > 0) {
      setSelectedFiles((current) => mergeFiles(current, accepted));
    }
    setLocalError(problems.length > 0 ? problems.join(" ") : null);
  };

  const handleRemoveFile = (name: string) => {
    setSelectedFiles((current) => current.filter((file) => file.name !== name));
  };

  const handleUpload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) {
      return;
    }
    setLocalError(null);
    if (selectedFiles.length === 0) {
      setLocalError(t("library.upload.errorFiles"));
      return;
    }
    onUploadFiles(selectedFiles);
    onClose();
  };

  const handleCreateText = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) {
      return;
    }
    setLocalError(null);
    const fileName = ensureTextFileName(textFileName);
    if (!isSafeTextFileName(fileName)) {
      setLocalError(t("library.upload.errorName"));
      return;
    }
    if (textContent.trim().length === 0) {
      setLocalError(t("library.upload.errorContent"));
      return;
    }
    if (textBytes > MAX_TEXT_BYTES) {
      setLocalError(t("library.upload.errorTextTooLarge"));
      return;
    }
    run.start(() =>
      textMutation.mutateAsync({
        data: { path: joinArchivePath(destination, fileName), content: textContent },
      }),
    );
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
      eyebrow={t("library.upload.eyebrow")}
      title={t("library.upload.title")}
      description={t("library.upload.description")}
      onClose={onClose}
      dismissible={!busy}
      className="library-intake"
    >
      <div
        className="library-tabs"
        role="tablist"
        aria-label={t("library.upload.methodAria")}
      >
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
          <Icon name="arrow-up" size={15} />
          {t("library.upload.uploadTab")}
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
          {t("library.upload.textTab")}
        </button>
      </div>

      {tab === "upload" ? (
        <UploadTabPanel
          uploadFileId={uploadFileId}
          uploadTabId={uploadTabId}
          uploadPanelId={uploadPanelId}
          destination={destination}
          selectedFiles={selectedFiles}
          localError={localError}
          submitLabel={uploadSubmit}
          onSubmit={handleUpload}
          onFileChange={handleFileChange}
          onRemoveFile={handleRemoveFile}
          onCancel={handleCancel}
        />
      ) : (
        <TextTabPanel
          textFileNameId={textFileNameId}
          textContentId={textContentId}
          textTabId={textTabId}
          textPanelId={textPanelId}
          destination={destination}
          textFileName={textFileName}
          textContent={textContent}
          textBytes={textBytes}
          busy={busy}
          path={textPath}
          phase={run.phase}
          job={run.job}
          localError={localError}
          failure={run.failure}
          canRetry={canRetry}
          submitLabel={textSubmit}
          onSubmit={handleCreateText}
          onFileNameChange={setTextFileName}
          onContentChange={setTextContent}
          onCancel={handleCancel}
          onRetry={handleRetry}
        />
      )}
    </LibraryDialog>
  );
}
