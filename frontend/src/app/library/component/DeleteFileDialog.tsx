import { useQueryClient } from "@tanstack/react-query";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useDeleteFile } from "../../generated-apis-types/files/files";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useToast } from "../../component/Toast";
import { LibraryDialog } from "./LibraryDialog";
import { describeError } from "./library-utils";

interface DeleteFileDialogProps {
  readonly file: FileSchema;
  readonly onClose: () => void;
  readonly onDeleted: () => void;
}

/**
 * Confirms the soft delete and says exactly what changes: the leaf disappears
 * from the current shelf and search while the version chain stays in history.
 */
export function DeleteFileDialog({ file, onClose, onDeleted }: DeleteFileDialogProps) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const deleteMutation = useDeleteFile({
    mutation: {
      onSuccess: () => {
        toast.success(`“${file.file_name}” was soft-deleted. Its history remains traceable.`);
        void queryClient.invalidateQueries();
        onDeleted();
      },
    },
  });

  const pending = deleteMutation.isPending;
  const error = deleteMutation.error ? describeError(deleteMutation.error) : null;

  return (
    <LibraryDialog
      eyebrow="Soft delete"
      title={`Delete “${file.file_name}”?`}
      description="This removes the current leaf from the shelf, search, and path listings. Nothing is erased: the version chain and earlier editions stay addressable through history."
      onClose={onClose}
      dismissible={!pending}
      className="library-confirm"
    >
      <div className="library-confirm__path">
        <span className="eyebrow">Path</span>
        <code>{file.raw_file_path}</code>
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
          onClick={() => deleteMutation.mutate({ fileId: file.id })}
          disabled={pending}
        >
          {pending ? "Soft-deleting…" : "Soft delete file"}
          <Icon name="history" size={15} />
        </Button>
      </div>
    </LibraryDialog>
  );
}
