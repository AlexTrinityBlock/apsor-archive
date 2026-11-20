import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { createFolder } from "../../generated-apis-types/folders/folders";
import { basename } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  invalidateLibraryQueries,
  isSafeFolderName,
  joinArchivePath,
  normalizeArchivePath,
} from "./library-utils";

interface NewFolderDialogProps {
  readonly currentPath: string;
  readonly onClose: () => void;
  readonly onCreated: (path: string) => void;
}

/**
 * Creates one branch folder inside the current shelf. The parent path is fixed
 * and only the leaf name is editable, so the dialog never turns into a second
 * path editor; the folder API creates it.
 */
export function NewFolderDialog({ currentPath, onClose, onCreated }: NewFolderDialogProps) {
  const { t } = useI18n();
  const baseId = useId();
  const nameId = `${baseId}-folder-name`;
  const queryClient = useQueryClient();
  const toast = useToast();
  const parentPath = normalizeArchivePath(currentPath) || "/";
  const [folderName, setFolderName] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    setServerError(null);
    const name = folderName.trim();
    if (!isSafeFolderName(name)) {
      setLocalError(t("library.newFolder.errorName"));
      return;
    }

    setPending(true);
    try {
      const directory = await createFolder({
        path: joinArchivePath(parentPath, name),
      });
      toast.success(
        t("library.newFolder.createdToast", { name: basename(directory.path) }),
      );
      invalidateLibraryQueries(queryClient, { paths: true });
      onCreated(directory.path);
    } catch (error) {
      setServerError(describeError(error));
    } finally {
      setPending(false);
    }
  };

  return (
    <LibraryDialog
      eyebrow={t("library.newFolder.eyebrow")}
      title={t("library.newFolder.title")}
      description={t("library.newFolder.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-new-folder"
    >
      <form className="library-form" onSubmit={handleSubmit}>
        <div className="library-field">
          <span className="library-field__label">
            {t("library.newFolder.parentLabel")}
          </span>
          <code className="library-fixed-path" data-page-context="exclude">
            {parentPath}
          </code>
          <span className="library-field__hint">
            {t("library.newFolder.parentHint")}
          </span>
        </div>

        <label className="library-field" htmlFor={nameId}>
          <span className="library-field__label">
            {t("library.newFolder.nameLabel")}
          </span>
          <input
            id={nameId}
            className="library-input"
            type="text"
            value={folderName}
            onChange={(event) => setFolderName(event.target.value)}
            placeholder="research"
            autoComplete="off"
            spellCheck={false}
            disabled={pending}
            data-autofocus
          />
          <span className="library-field__hint">
            {t("library.newFolder.nameHint")}
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
            {t("library.common.cancel")}
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={pending}>
            {pending ? t("library.newFolder.creating") : t("library.newFolder.submit")}
            <Icon name="folder" size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
