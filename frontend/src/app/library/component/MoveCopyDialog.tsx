import { useId, useState, type FormEvent } from "react";

import type { FileSchema, PathFileSchema } from "../../generated-apis-types/schemas";
import { copyFile, moveFile } from "../../generated-apis-types/files/files";
import { basename, parentPath } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  isSafeUploadName,
  joinArchivePath,
  normalizeArchivePath,
  sameArchivePath,
} from "./library-utils";

type FileOperationMode = "move" | "copy";

interface MoveCopyDialogProps {
  readonly file: PathFileSchema;
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
  const verb = mode === "move" ? "Move" : "Copy";
  const progressLabel = mode === "move" ? "Moving…" : "Copying…";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    setServerError(null);
    if (normalizedFolder.length === 0) {
      setLocalError("Choose a destination folder.");
      return;
    }
    if (!isSafeUploadName(normalizedName)) {
      setLocalError("Enter one file name without slashes.");
      return;
    }
    if (mode === "move" && isCurrentPath) {
      setLocalError(
        "That is the file's current path. Choose a different branch folder or file name.",
      );
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
      eyebrow={mode === "move" ? "Move leaf" : "Copy leaf"}
      title={`${verb} “${file.file_name}”`}
      description={
        mode === "move"
          ? "Move keeps the same file id, version, and chunks; only the branch path changes. The reader link follows the new path."
          : "Copy creates a new file id with fresh chunks and leaves the original leaf untouched."
      }
      onClose={onClose}
      dismissible={!pending}
      className="library-move-copy"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">Current path</span>
        <code>{file.raw_file_path}</code>
      </div>

      <form className="library-form" onSubmit={handleSubmit}>
        <label className="library-field" htmlFor={folderId}>
          <span className="library-field__label">Destination folder</span>
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
            Full folder path. Missing folders are created by the archive.
          </span>
        </label>

        {suggestions.length > 0 ? (
          <div className="library-move__suggestions" aria-label="Suggested destination folders">
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
                {suggestion === "/" ? "Archive root" : basename(suggestion)}
              </button>
            ))}
          </div>
        ) : null}

        <label className="library-field" htmlFor={nameId}>
          <span className="library-field__label">File name</span>
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
          <span className="eyebrow">Destination path</span>
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
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={pending}>
            {pending ? progressLabel : `${verb} file`}
            <Icon name={mode === "move" ? "branch" : "copy"} size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
