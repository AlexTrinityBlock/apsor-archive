import { useQueryClient } from "@tanstack/react-query";

import { useDeleteFile } from "../../generated-apis-types/files/files";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
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
  const toast = useToast();
  const queryClient = useQueryClient();

  const deleteMutation = useDeleteFile({
    mutation: {
      onSuccess: () => {
        toast.success(`“${fileName}” was soft-deleted. Its history remains traceable.`);
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
      eyebrow="Soft delete"
      title={`Delete “${fileName}”?`}
      description="This removes the current file from the shelf, search, and path listings. Nothing is erased: the version chain and earlier editions stay addressable through history."
      onClose={onClose}
      dismissible={!pending}
      className="library-confirm"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">Path</span>
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
          Keep file
        </Button>
        <Button
          variant="primary"
          size="sm"
          className="library-delete-confirm"
          onClick={() => deleteMutation.mutate({ fileId })}
          disabled={pending}
        >
          {pending ? "Soft-deleting…" : "Soft delete file"}
          <Icon name="history" size={15} />
        </Button>
      </div>
    </LibraryDialog>
  );
}
