import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type {
  DirectorySchema,
  LibraryDeleteResultSchema,
  PathFileSchema,
} from "../../generated-apis-types/schemas";
import { useDeleteLibrarySelection } from "../../generated-apis-types/files/files";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import { describeError, invalidateLibraryQueries } from "./library-utils";

const FOLDER_PREVIEW_LIMIT = 5;

interface DeleteSelectionDialogProps {
  readonly files: readonly PathFileSchema[];
  readonly folders: readonly DirectorySchema[];
  readonly onClose: () => void;
  readonly onDeleted: (result: LibraryDeleteResultSchema) => void;
}

/**
 * Confirms one atomic batch soft delete.
 *
 * Folder deletion is recursive, so the dialog spells out that every current
 * file and subfolder below the selected branches disappears from listings
 * while earlier versions and stored original bytes remain readable by id. A
 * folder selection requires an explicit acknowledgement before submitting.
 */
export function DeleteSelectionDialog({
  files,
  folders,
  onClose,
  onDeleted,
}: DeleteSelectionDialogProps) {
  const { t, formatNumber } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [acknowledged, setAcknowledged] = useState(false);

  const hasFolders = folders.length > 0;
  const total = files.length + folders.length;

  const deleteMutation = useDeleteLibrarySelection({
    mutation: {
      onSuccess: (result) => {
        let fileDetail: string | null = null;
        if (result.deleted_files > 0) {
          fileDetail = t(
            result.deleted_files === 1
              ? "library.units.fileOne"
              : "library.units.fileOther",
            { count: formatNumber(result.deleted_files) },
          );
        }
        let folderDetail: string | null = null;
        if (result.deleted_folders > 0) {
          folderDetail = t(
            result.deleted_folders === 1
              ? "library.units.folderOne"
              : "library.units.folderOther",
            { count: formatNumber(result.deleted_folders) },
          );
        }
        const detail = [fileDetail, folderDetail]
          .filter((part): part is string => part !== null)
          .join(" · ");
        const deletedTotal = result.deleted_files + result.deleted_folders;
        toast.success(
          t(
            deletedTotal === 1
              ? "library.batchDelete.deletedToastOne"
              : "library.batchDelete.deletedToastOther",
            { count: formatNumber(deletedTotal), detail },
          ),
        );
        invalidateLibraryQueries(queryClient, {
          paths: true,
          stats: true,
          timeline: true,
          search: true,
          fileIds: result.deleted_file_ids,
        });
        onDeleted(result);
      },
    },
  });

  const pending = deleteMutation.isPending;
  const error = deleteMutation.error ? describeError(deleteMutation.error) : null;
  const canSubmit = total > 0 && (!hasFolders || acknowledged);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending || !canSubmit) {
      return;
    }
    deleteMutation.mutate({
      data: {
        file_ids: files.map((file) => file.file_id),
        folder_paths: folders.map((folder) => folder.path),
      },
    });
  };

  return (
    <LibraryDialog
      eyebrow={t("library.batchDelete.eyebrow")}
      title={t(
        total === 1
          ? "library.batchDelete.titleOne"
          : "library.batchDelete.titleOther",
        { count: formatNumber(total) },
      )}
      description={t("library.batchDelete.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-batch-delete"
    >
      <form className="library-form" onSubmit={handleSubmit}>
        <div className="library-batch-delete__summary">
          <span className="library-batch-delete__count">
            <Icon name="file" size={14} />
            {t(
              files.length === 1
                ? "library.batchDelete.filesCountOne"
                : "library.batchDelete.filesCountOther",
              { count: formatNumber(files.length) },
            )}
          </span>
          <span className="library-batch-delete__count">
            <Icon name="folder" size={14} />
            {t(
              folders.length === 1
                ? "library.batchDelete.foldersCountOne"
                : "library.batchDelete.foldersCountOther",
              { count: formatNumber(folders.length) },
            )}
          </span>
        </div>

        {hasFolders ? (
          <div className="library-batch-delete__folders">
            <span className="eyebrow">{t("library.batchDelete.foldersHeading")}</span>
            <ul className="library-batch-delete__folder-list">
              {folders.slice(0, FOLDER_PREVIEW_LIMIT).map((folder) => (
                <li key={folder.path}>
                  <Icon name="folder" size={12} />
                  <code title={folder.path}>{folder.name}</code>
                </li>
              ))}
              {folders.length > FOLDER_PREVIEW_LIMIT ? (
                <li className="library-batch-delete__more">
                  {t("library.batchDelete.more", {
                    count: formatNumber(folders.length - FOLDER_PREVIEW_LIMIT),
                  })}
                </li>
              ) : null}
            </ul>
          </div>
        ) : null}

        <div className="library-batch-delete__warning">
          <p className="library-batch-delete__warning-title">
            <Icon name="info" size={14} />
            {t("library.batchDelete.warningTitle")}
          </p>
          <ul className="library-batch-delete__warning-list">
            <li>
              {hasFolders
                ? t("library.batchDelete.warningRecursive")
                : t("library.batchDelete.warningFiles")}
            </li>
            <li>{t("library.batchDelete.warningHistory")}</li>
            <li>{t("library.batchDelete.warningRoot")}</li>
          </ul>
        </div>

        {hasFolders ? (
          <label className="library-checkbox library-batch-delete__ack">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              disabled={pending}
            />
            <span className="library-checkbox__box" aria-hidden="true">
              <Icon name="check" size={12} />
            </span>
            <span className="library-batch-delete__ack-text">
              {t("library.batchDelete.ack")}
            </span>
          </label>
        ) : null}

        {error ? (
          <p className="library-form__error" role="alert">
            <Icon name="info" size={15} />
            <span>
              <strong>{t("library.batchDelete.error")}</strong> {error}
            </span>
          </p>
        ) : null}

        <div className="library-form__actions">
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={pending}
            data-autofocus
          >
            {t("library.common.cancel")}
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            className="library-delete-confirm"
            disabled={pending || !canSubmit}
          >
            {pending
              ? t("library.batchDelete.pending")
              : t("library.batchDelete.submit")}
            <Icon name="trash" size={15} />
          </Button>
        </div>
      </form>
    </LibraryDialog>
  );
}
