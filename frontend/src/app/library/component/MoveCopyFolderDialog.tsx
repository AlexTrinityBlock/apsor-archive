import { useId, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type {
  DirectorySchema,
  FolderMutationSchema,
} from "../../generated-apis-types/schemas";
import {
  copyFolder,
  moveFolder,
} from "../../generated-apis-types/folders/folders";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import {
  describeError,
  invalidateLibraryQueries,
  isPathInside,
  isSafeFolderName,
  joinArchivePath,
  normalizeArchivePath,
  sameArchivePath,
  type FileOperationMode,
} from "./library-utils";

interface MoveCopyFolderDialogProps {
  readonly folder: DirectorySchema;
  readonly mode: FileOperationMode;
  readonly currentPath: string;
  readonly onClose: () => void;
  readonly onDone: (
    result: FolderMutationSchema,
    mode: FileOperationMode,
  ) => void;
}

/**
 * Moves or copies one folder subtree. Both operations take a complete
 * destination path; the archive owns collisions, descendant checks, and the
 * copy size ceiling, while the dialog mirrors the path rules for fast feedback.
 */
export function MoveCopyFolderDialog({
  folder,
  mode,
  currentPath,
  onClose,
  onDone,
}: MoveCopyFolderDialogProps) {
  const { t, formatNumber } = useI18n();
  const baseId = useId();
  const folderId = `${baseId}-destination-folder`;
  const nameId = `${baseId}-destination-name`;
  const queryClient = useQueryClient();
  const toast = useToast();
  const [targetFolder, setTargetFolder] = useState(currentPath);
  const [targetName, setTargetName] = useState(() =>
    mode === "copy"
      ? t("library.folderCopy.copyName", { name: folder.name })
      : folder.name,
  );
  const [localError, setLocalError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const normalizedFolder = normalizeArchivePath(targetFolder);
  const normalizedName = targetName.trim();
  const targetPath = joinArchivePath(normalizedFolder, normalizedName);
  const progressLabel =
    mode === "move"
      ? t("library.folderMoveCopy.moving")
      : t("library.folderMoveCopy.copying");
  const submitLabel =
    mode === "move"
      ? t("library.folderMoveCopy.submitMove")
      : t("library.folderMoveCopy.submitCopy");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError(null);
    setServerError(null);
    if (normalizedFolder.length === 0) {
      setLocalError(t("library.folderMoveCopy.errorFolder"));
      return;
    }
    if (!isSafeFolderName(normalizedName)) {
      setLocalError(t("library.folderMoveCopy.errorName"));
      return;
    }
    if (sameArchivePath(targetPath, folder.path)) {
      setLocalError(t("library.folderMoveCopy.errorCurrent"));
      return;
    }
    if (isPathInside(targetPath, folder.path)) {
      setLocalError(t("library.folderMoveCopy.errorInsideSelf"));
      return;
    }

    setPending(true);
    try {
      const result =
        mode === "move"
          ? await moveFolder({
              path: folder.path,
              target_path: targetPath,
            })
          : await copyFolder({
              path: folder.path,
              target_path: targetPath,
            });
      const folderCount = t(
        result.affected_folders === 1
          ? "library.units.folderOne"
          : "library.units.folderOther",
        { count: formatNumber(result.affected_folders) },
      );
      const fileCount = t(
        result.affected_files === 1
          ? "library.units.fileOne"
          : "library.units.fileOther",
        { count: formatNumber(result.affected_files) },
      );
      toast.success(
        t(
          mode === "move"
            ? "library.folderMoveCopy.movedToast"
            : "library.folderMoveCopy.copiedToast",
          {
            name: result.folder.name,
            folders: folderCount,
            files: fileCount,
          },
        ),
      );
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        search: true,
      });
      if (mode === "move") {
        // Move rewrites raw_file_path for every current file below the branch;
        // invalidate open file details so they do not keep the old path.
        void queryClient.invalidateQueries({ queryKey: ["/api/v1/files"] });
      }
      onDone(result, mode);
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
          ? t("library.folderMoveCopy.eyebrowMove")
          : t("library.folderMoveCopy.eyebrowCopy")
      }
      title={
        mode === "move"
          ? t("library.folderMoveCopy.titleMove", { name: folder.name })
          : t("library.folderMoveCopy.titleCopy", { name: folder.name })
      }
      description={
        mode === "move"
          ? t("library.folderMoveCopy.descriptionMove")
          : t("library.folderMoveCopy.descriptionCopy")
      }
      onClose={onClose}
      dismissible={!pending}
      className="library-folder-move-copy"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">{t("library.folderMoveCopy.currentPath")}</span>
        <code>{folder.path}</code>
      </div>

      <form className="library-form" onSubmit={handleSubmit}>
        <label className="library-field" htmlFor={folderId}>
          <span className="library-field__label">
            {t("library.folderMoveCopy.destinationFolder")}
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
            {t("library.folderMoveCopy.folderHint")}
          </span>
        </label>

        <label className="library-field" htmlFor={nameId}>
          <span className="library-field__label">
            {t("library.folderMoveCopy.folderName")}
          </span>
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
          <span className="eyebrow">
            {t("library.folderMoveCopy.destinationPath")}
          </span>
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
