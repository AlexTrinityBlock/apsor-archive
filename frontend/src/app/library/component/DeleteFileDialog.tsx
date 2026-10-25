import { useQueryClient } from "@tanstack/react-query";

import { useDeleteFile } from "../../generated-apis-types/files/files";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { LibraryDialog } from "./LibraryDialog";
import { describeError, invalidateLibraryQueries } from "./library-utils";

interface DeleteFileDialogProps {
  readonly fileId: number;
  readonly fileName: string;
  readonly rawFilePath: string;
  readonly onClose: () => void;
  readonly onDeleted: () => void;
}

/**
 * Confirms the soft delete and says exactly what changes: the file disappears
 * from the current shelf and search while the version chain stays in history.
 */
export function DeleteFileDialog({
  fileId,
  fileName,
  rawFilePath,
  onClose,
  onDeleted,
}: DeleteFileDialogProps) {
  const { t } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();

  const deleteMutation = useDeleteFile({
    mutation: {
      onSuccess: () => {
        toast.success(t("library.delete.deletedToast", { name: fileName }));
        invalidateLibraryQueries(queryClient, {
          paths: true,
          stats: true,
          timeline: true,
          search: true,
          fileIds: [fileId],
        });
        onDeleted();
      },
    },
  });

  const pending = deleteMutation.isPending;
  const error = deleteMutation.error ? describeError(deleteMutation.error) : null;

  return (
    <LibraryDialog
      eyebrow={t("library.delete.eyebrow")}
      title={t("library.delete.title", { name: fileName })}
      description={t("library.delete.description")}
      onClose={onClose}
      dismissible={!pending}
      className="library-confirm"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">{t("library.delete.path")}</span>
        <code>{rawFilePath}</code>
      </div>

      {error ? (
        <p className="library-form__error" role="alert">
          <Icon name="info" size={15} />
          <span>{error}</span>
        </p>
      ) : null}

      <div className="library-form__actions">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={pending}>
          {t("library.delete.keep")}
        </Button>
        <Button
          variant="primary"
          size="sm"
          className="library-delete-confirm"
          onClick={() => deleteMutation.mutate({ fileId })}
          disabled={pending}
        >
          {pending ? t("library.delete.pending") : t("library.delete.submit")}
          <Icon name="history" size={15} />
        </Button>
      </div>
    </LibraryDialog>
  );
}
