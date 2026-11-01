import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type {
  DirectorySchema,
  FolderMutationSchema,
} from "../../generated-apis-types/schemas";
import { renameFolder } from "../../generated-apis-types/folders/folders";
import { parentPath } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  invalidateLibraryQueries,
  isSafeFolderName,
} from "./library-utils";

interface RenameFolderDialogProps {
  readonly folder: DirectorySchema;
  readonly onClose: () => void;
  readonly onRenamed: (result: FolderMutationSchema) => void;
}

/**
 * Renames one folder in place. The parent stays fixed, so only a single leaf
 * name is editable; the archive rewrites every path below it on success.
 */
export function RenameFolderDialog({
  folder,
  onClose,
  onRenamed,
}: RenameFolderDialogProps) {
  const { t } = useI18n();
  const baseId = useId();
  const nameId = `${baseId}-folder-name`;
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(folder.name);
  const [localError, setLocalError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const trimmedName = name.trim();
  const unchanged = trimmedName === folder.name;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    setServerError(null);
    if (unchanged) {
      return;
    }
    if (!isSafeFolderName(trimmedName)) {
      setLocalError(t("library.folderRename.errorName"));
      return;
    }

    setPending(true);
    try {
      const result = await renameFolder({
        path: folder.path,
        new_name: trimmedName,
      });
      toast.success(
        t("library.folderRename.renamedToast", { name: result.folder.name }),
      );
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        search: true,
      });
      // Folder paths changed for every current file below the branch, so any
      // open file detail must refetch its new raw_file_path.
      void queryClient.invalidateQueries({ queryKey: ["/api/v1/files"] });
      onRenamed(result);
    } catch (error) {
      setServerError(describeError(error));
    } finally {
      setPending(false);
    }
  };

  return (
    <LibraryDialog
      eyebrow={t("library.folderRename.eyebrow")}
      title={t("library.folderRename.title", { name: folder.name })}
      description={t("library.folderRename.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-folder-rename"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">{t("library.rename.folder")}</span>
        <code>{parentPath(folder.path)}</code>
      </div>

      <form className="library-form" onSubmit={handleSubmit}>
        <label className="library-field" htmlFor={nameId}>
          <span className="library-field__label">
            {t("library.folderRename.nameLabel")}
          </span>
          <input
            id={nameId}
            className="library-input"
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            data-autofocus
          />
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
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={pending || unchanged}
          >
            {pending ? t("library.rename.pending") : t("library.common.rename")}
            <Icon name="pencil" size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
