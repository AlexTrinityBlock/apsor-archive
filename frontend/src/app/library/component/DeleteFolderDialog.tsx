import { useQueryClient } from "@tanstack/react-query";

import type {
  DirectorySchema,
  LibraryDeleteResultSchema,
} from "../../generated-apis-types/schemas";
import { useDeleteLibrarySelection } from "../../generated-apis-types/files/files";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import { describeError, invalidateLibraryQueries } from "./library-utils";

interface DeleteFolderDialogProps {
  readonly folder: DirectorySchema;
  readonly onClose: () => void;
  readonly onDeleted: (result: LibraryDeleteResultSchema) => void;
}

/**
 * Confirms the recursive soft delete of one folder subtree. The dialog spells
 * out that the branch leaves the Library and search while file history and
 * stored original bytes remain readable by id.
 */
export function DeleteFolderDialog({
  folder,
  onClose,
  onDeleted,
}: DeleteFolderDialogProps) {
  const { t, formatNumber } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();

  const deleteMutation = useDeleteLibrarySelection({
    mutation: {
      onSuccess: (result) => {
        const fileCount = t(
          result.deleted_files === 1
            ? "library.units.fileOne"
            : "library.units.fileOther",
          { count: formatNumber(result.deleted_files) },
        );
        const folderCount = t(
          result.deleted_folders === 1
            ? "library.units.folderOne"
            : "library.units.folderOther",
          { count: formatNumber(result.deleted_folders) },
        );
        toast.success(
          t("library.folderDelete.deletedToast", {
            name: folder.name,
            files: fileCount,
            folders: folderCount,
          }),
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

  return (
    <LibraryDialog
      eyebrow={t("library.folderDelete.eyebrow")}
      title={t("library.folderDelete.title", { name: folder.name })}
      description={t("library.folderDelete.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-confirm library-folder-delete"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">{t("library.folderDelete.path")}</span>
        <code>{folder.path}</code>
      </div>

      <div className="library-batch-delete__warning">
        <p className="library-batch-delete__warning-title">
          <Icon name="info" size={14} />
          {t("library.folderDelete.eyebrow")}
        </p>
        <p className="library-folder-delete__warning-text">
          {t("library.folderDelete.warning")}
        </p>
      </div>

      {error ? (
        <p className="library-form__error" role="alert">
          <Icon name="info" size={15} />
          <span>{error}</span>
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
          variant="primary"
          size="sm"
          className="library-delete-confirm"
          onClick={() => deleteMutation.mutate({ data: { folder_paths: [folder.path] } })}
          disabled={pending}
        >
          {pending
            ? t("library.folderDelete.pending")
            : t("library.folderDelete.submit")}
          <Icon name="trash" size={15} />
        </Button>
      </div>
    </LibraryDialog>
  );
}
