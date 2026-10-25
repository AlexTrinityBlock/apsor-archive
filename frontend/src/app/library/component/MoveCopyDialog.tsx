import { useId, useState, type FormEvent } from "react";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { copyFile, moveFile } from "../../generated-apis-types/files/files";
import { basename, parentPath } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  isSafeUploadName,
  joinArchivePath,
  normalizeArchivePath,
  sameArchivePath,
  type FileOperationTarget,
} from "./library-utils";

type FileOperationMode = "move" | "copy";

interface MoveCopyDialogProps {
  readonly file: FileOperationTarget;
  readonly mode: FileOperationMode;
  readonly currentPath: string;
  readonly suggestions: readonly string[];
  readonly onClose: () => void;
  readonly onDone: (file: FileSchema, targetFolder: string, mode: FileOperationMode) => void;
}

function defaultFolder(
  filePath: string,
  currentPath: string,
  suggestions: readonly string[],
): string {
  const currentFolder = parentPath(filePath);
  return (
    suggestions.find((candidate) => !sameArchivePath(candidate, currentFolder)) ??
    (sameArchivePath(currentPath, currentFolder) ? "/" : currentPath)
  );
}

/**
 * Explicit touch/keyboard path for moving or copying a leaf. The server owns
 * path collisions, so an occupied destination error is shown verbatim.
 */
export function MoveCopyDialog({
  file,
  mode,
  currentPath,
  suggestions,
  onClose,
  onDone,
}: MoveCopyDialogProps) {
  const { t } = useI18n();
  const baseId = useId();
  const folderId = `${baseId}-destination-folder`;
  const nameId = `${baseId}-destination-name`;
  const [targetFolder, setTargetFolder] = useState(() =>
    defaultFolder(file.raw_file_path, currentPath, suggestions),
  );
  const [targetName, setTargetName] = useState(file.file_name);
  const [localError, setLocalError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const normalizedFolder = normalizeArchivePath(targetFolder);
  const normalizedName = targetName.trim();
  const targetPath = joinArchivePath(normalizedFolder, normalizedName);
  const isCurrentPath = sameArchivePath(targetPath, file.raw_file_path);
  const progressLabel =
    mode === "move" ? t("library.moveCopy.moving") : t("library.moveCopy.copying");
  const submitLabel =
    mode === "move" ? t("library.moveCopy.submitMove") : t("library.moveCopy.submitCopy");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    setServerError(null);
    if (normalizedFolder.length === 0) {
      setLocalError(t("library.moveCopy.errorFolder"));
      return;
    }
    if (!isSafeUploadName(normalizedName)) {
      setLocalError(t("library.moveCopy.errorName"));
      return;
    }
    if (mode === "move" && isCurrentPath) {
      setLocalError(t("library.moveCopy.errorCurrent"));
      return;
    }

    setPending(true);
    try {
      const result =
        mode === "move"
          ? await moveFile(file.file_id, { path: targetPath })
          : await copyFile(file.file_id, { path: targetPath });
      onDone(result, normalizedFolder, mode);
    } catch (error) {
      setServerError(describeError(error));
    } finally {
      setPending(false);
    }
  };

  return (
    <LibraryDialog
      eyebrow={
        mode === "move"
          ? t("library.moveCopy.eyebrowMove")
          : t("library.moveCopy.eyebrowCopy")
      }
      title={
        mode === "move"
          ? t("library.moveCopy.titleMove", { name: file.file_name })
          : t("library.moveCopy.titleCopy", { name: file.file_name })
      }
      description={
        mode === "move"
          ? t("library.moveCopy.descriptionMove")
          : t("library.moveCopy.descriptionCopy")
      }
      onClose={onClose}
      dismissible={!pending}
      className="library-move-copy"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">{t("library.moveCopy.currentPath")}</span>
        <code>{file.raw_file_path}</code>
      </div>

      <form className="library-form" onSubmit={handleSubmit}>
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

        <label className="library-field" htmlFor={nameId}>
          <span className="library-field__label">{t("library.moveCopy.fileName")}</span>
          <input
            id={nameId}
            className="library-input"
            type="text"
            value={targetName}
            onChange={(event) => setTargetName(event.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>

        <div className="library-move__preview">
          <span className="eyebrow">{t("library.moveCopy.destinationPath")}</span>
          <code>{targetPath || "—"}</code>
        </div>

        {localError ? (
          <p className="library-form__error" role="alert">
            <Icon name="info" size={15} />
            <span>{localError}</span>
          </p>
        ) : null}
        {serverError ? (
          <p className="library-form__error" role="alert">
            <Icon name="info" size={15} />
            <span>{serverError}</span>
          </p>
        ) : null}

        <div className="library-form__actions">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={pending}>
            {t("library.common.cancel")}
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={pending}>
            {pending ? progressLabel : submitLabel}
            <Icon name={mode === "move" ? "branch" : "copy"} size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
