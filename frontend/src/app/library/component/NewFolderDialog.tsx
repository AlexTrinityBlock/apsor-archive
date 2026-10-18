import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { createFolder } from "../../generated-apis-types/folders/folders";
import { basename } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  normalizeArchivePath,
  sameArchivePath,
} from "./library-utils";

interface NewFolderDialogProps {
  readonly currentPath: string;
  readonly onClose: () => void;
  readonly onCreated: (path: string) => void;
}

function pathPrefix(path: string): string {
  const normalized = normalizeArchivePath(path);
  return normalized === "/" ? "/" : `${normalized}/`;
}

/**
 * Creates one branch folder inside the current shelf. The server also creates
 * missing ancestors and returns the existing directory for an idempotent call.
 */
export function NewFolderDialog({ currentPath, onClose, onCreated }: NewFolderDialogProps) {
  const baseId = useId();
  const pathId = `${baseId}-folder-path`;
  const queryClient = useQueryClient();
  const toast = useToast();
  const [folderPath, setFolderPath] = useState(() => pathPrefix(currentPath));
  const [localError, setLocalError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    setServerError(null);
    const normalized = normalizeArchivePath(folderPath);
    if (normalized === "/" || normalized.length === 0) {
      setLocalError("Name the new folder inside the current branch.");
      return;
    }
    if (sameArchivePath(normalized, currentPath)) {
      setLocalError("That is the current folder. Add a new name inside it.");
      return;
    }

    setPending(true);
    try {
      const directory = await createFolder({ path: normalized });
      toast.success(`Folder “${basename(directory.path)}” is ready.`);
      void queryClient.invalidateQueries();
      onCreated(directory.path);
    } catch (error) {
      setServerError(describeError(error));
    } finally {
      setPending(false);
    }
  };

  return (
    <LibraryDialog
      eyebrow="New branch"
      title="Create a folder"
      description="Folders create the branch that file leaves sit on. Missing parents are created automatically, and an existing folder is returned as ready. A path already occupied by a file is rejected by the archive."
      onClose={onClose}
      dismissible={!pending}
      className="library-new-folder"
    >
      <form className="library-form" onSubmit={handleSubmit}>
        <label className="library-field" htmlFor={pathId}>
          <span className="library-field__label">Folder path</span>
          <input
            id={pathId}
            className="library-input"
            type="text"
            value={folderPath}
            onChange={(event) => setFolderPath(event.target.value)}
            placeholder="/notes/research"
            autoComplete="off"
            spellCheck={false}
            data-autofocus
          />
          <span className="library-field__hint">
            Full archive path. Current branch: <code>{currentPath}</code>
          </span>
        </label>

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
            {pending ? "Creating…" : "Create folder"}
            <Icon name="folder" size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
