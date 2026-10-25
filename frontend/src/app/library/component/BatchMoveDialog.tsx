import { useId, useState, type FormEvent } from "react";

import type { PathFileSchema } from "../../generated-apis-types/schemas";
import { moveFile } from "../../generated-apis-types/files/files";
import { basename, parentPath } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  joinArchivePath,
  normalizeArchivePath,
  sameArchivePath,
} from "./library-utils";

export interface BatchMoveFailure {
  readonly fileId: number;
  readonly fileName: string;
  readonly message: string;
}

export interface BatchMoveResult {
  readonly movedIds: readonly number[];
  readonly failures: readonly BatchMoveFailure[];
  readonly skipped: number;
  readonly targetFolder: string;
}

interface BatchMoveDialogProps {
  readonly files: readonly PathFileSchema[];
  readonly currentPath: string;
  readonly suggestions: readonly string[];
  readonly onClose: () => void;
  readonly onFinished: (result: BatchMoveResult) => void;
}

function defaultFolder(currentPath: string, suggestions: readonly string[]): string {
  return (
    suggestions.find((candidate) => !sameArchivePath(candidate, currentPath)) ?? ""
  );
}

function BatchMoveSummary({
  result,
  onClose,
}: {
  readonly result: BatchMoveResult;
  readonly onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  return (
    <>
      <div className="library-batch__summary" role="status">
        <p>
          {t(
            result.movedIds.length === 1
              ? "library.batch.movedSummaryOne"
              : "library.batch.movedSummaryOther",
            {
              count: formatNumber(result.movedIds.length),
              folder: result.targetFolder,
            },
          )}
        </p>
        {result.skipped > 0 ? (
          <p className="library-batch__note">
            {t(
              result.skipped === 1
                ? "library.batch.skippedSummaryOne"
                : "library.batch.skippedSummaryOther",
              { count: formatNumber(result.skipped) },
            )}
          </p>
        ) : null}
        {result.failures.length > 0 ? (
          <>
            <p className="library-batch__failures-title">
              {t(
                result.failures.length === 1
                  ? "library.batch.failuresSummaryOne"
                  : "library.batch.failuresSummaryOther",
                { count: formatNumber(result.failures.length) },
              )}
            </p>
            <ul className="library-batch__failures">
              {result.failures.map((failure) => (
                <li key={failure.fileId}>
                  <code>{failure.fileName}</code>
                  <span>{failure.message}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
      <div className="library-form__actions">
        <Button variant="primary" size="sm" onClick={onClose}>
          {t("library.common.done")}
          <Icon name="check" size={15} />
        </Button>
      </div>
    </>
  );
}

/**
 * Moves several selected leaves into one destination folder.
 *
 * Requests run one at a time so a large selection cannot flood the API and each
 * file gets its own success/failure result. Successful moves are never rolled
 * back when a later file collides with an occupied path.
 */
export function BatchMoveDialog({
  files,
  currentPath,
  suggestions,
  onClose,
  onFinished,
}: BatchMoveDialogProps) {
  const { t, formatNumber } = useI18n();
  const baseId = useId();
  const folderId = `${baseId}-destination-folder`;
  const [targetFolder, setTargetFolder] = useState(() =>
    defaultFolder(currentPath, suggestions),
  );
  const [pending, setPending] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [result, setResult] = useState<BatchMoveResult | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const normalizedFolder = normalizeArchivePath(targetFolder);
  const fileCount = files.length;
  const submitLabel = t(
    fileCount === 1 ? "library.batch.submitOne" : "library.batch.submitOther",
    { count: formatNumber(fileCount) },
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    if (normalizedFolder.length === 0) {
      setLocalError(t("library.moveCopy.errorFolder"));
      return;
    }

    const filesToMove = files.filter(
      (file) => !sameArchivePath(parentPath(file.raw_file_path), normalizedFolder),
    );
    const skipped = fileCount - filesToMove.length;
    const movedIds: number[] = [];
    const failures: BatchMoveFailure[] = [];

    setPending(true);
    setProgress({ done: 0, total: filesToMove.length });
    for (const [index, file] of filesToMove.entries()) {
      try {
        await moveFile(file.file_id, {
          path: joinArchivePath(normalizedFolder, file.file_name),
        });
        movedIds.push(file.file_id);
      } catch (error) {
        failures.push({
          fileId: file.file_id,
          fileName: file.file_name,
          message: describeError(error),
        });
      }
      setProgress({ done: index + 1, total: filesToMove.length });
    }

    const summary: BatchMoveResult = {
      movedIds,
      failures,
      skipped,
      targetFolder: normalizedFolder,
    };
    setPending(false);
    setProgress(null);
    setResult(summary);
    onFinished(summary);
  };

  return (
    <LibraryDialog
      eyebrow={t("library.batch.eyebrow")}
      title={t(
        fileCount === 1 ? "library.batch.titleOne" : "library.batch.titleOther",
        { count: formatNumber(fileCount) },
      )}
      description={t("library.batch.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-move-copy library-batch-move"
    >
      {result ? (
        <BatchMoveSummary result={result} onClose={onClose} />
      ) : (
        <form className="library-form" onSubmit={handleSubmit}>
          <div className="library-confirm__path">
            <span className="eyebrow">{t("library.batch.selectedFiles")}</span>
            <ul className="library-batch__files">
              {files.slice(0, 6).map((file) => (
                <li key={file.file_id}>
                  <Icon name="leaf" size={12} />
                  <code>{file.raw_file_path}</code>
                </li>
              ))}
              {fileCount > 6 ? (
                <li>{t("library.batch.more", { count: formatNumber(fileCount - 6) })}</li>
              ) : null}
            </ul>
          </div>

          <label className="library-field" htmlFor={folderId}>
            <span className="library-field__label">
              {t("library.moveCopy.destinationFolder")}
            </span>
            <input
              id={folderId}
              className="library-input"
              type="text"
              value={targetFolder}
              onChange={(event) => setTargetFolder(event.target.value)}
              placeholder="/notes/research"
              autoComplete="off"
              spellCheck={false}
              data-autofocus
              disabled={pending}
            />
            <span className="library-field__hint">
              {t("library.moveCopy.folderHint")}
            </span>
          </label>

          {suggestions.length > 0 ? (
            <div
              className="library-move__suggestions"
              aria-label={t("library.moveCopy.suggestionsAria")}
            >
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className={[
                    "library-move__chip",
                    sameArchivePath(suggestion, normalizedFolder) ? "is-active" : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onClick={() => setTargetFolder(suggestion)}
                  disabled={pending}
                >
                  <Icon name="folder" size={12} />
                  {suggestion === "/"
                    ? t("library.common.archiveRoot")
                    : basename(suggestion)}
                </button>
              ))}
            </div>
          ) : null}

          <div className="library-move__preview">
            <span className="eyebrow">{t("library.moveCopy.destinationFolder")}</span>
            <code>{normalizedFolder || "—"}</code>
          </div>

          {localError ? (
            <p className="library-form__error" role="alert">
              <Icon name="info" size={15} />
              <span>{localError}</span>
            </p>
          ) : null}

          <div className="library-form__actions">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={pending}>
              {t("library.common.cancel")}
            </Button>
            <Button type="submit" variant="primary" size="sm" disabled={pending}>
              {pending && progress
                ? t("library.batch.movingProgress", {
                    done: formatNumber(progress.done),
                    total: formatNumber(progress.total),
                  })
                : submitLabel}
              <Icon name="branch" size={15} />
            </Button>
          </div>
        </form>
      )}
    </LibraryDialog>
  );
}
