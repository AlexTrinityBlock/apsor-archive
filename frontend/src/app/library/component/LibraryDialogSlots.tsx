import type {
  DirectorySchema,
  FolderMutationSchema,
  LibraryDeleteResultSchema,
  PathFileSchema,
} from "../../generated-apis-types/schemas";
import { DeleteFolderDialog } from "./DeleteFolderDialog";
import { DeleteSelectionDialog } from "./DeleteSelectionDialog";
import { LibrarySelectionBar } from "./LibrarySelectionBar";
import { MoveCopyFolderDialog } from "./MoveCopyFolderDialog";
import { RenameFileDialog } from "./RenameFileDialog";
import { RenameFolderDialog } from "./RenameFolderDialog";
import type {
  FileOperationMode,
  FileOperationTarget,
  LibraryTab,
} from "./library-utils";

export interface FolderMoveCopyRequest {
  readonly folder: DirectorySchema;
  readonly mode: FileOperationMode;
}

export interface DeleteSelectionRequest {
  readonly files: readonly PathFileSchema[];
  readonly folders: readonly DirectorySchema[];
  readonly afterDeletePath?: string | null;
}

interface RenameRequestDialogProps {
  readonly request: FileOperationTarget | null;
  readonly onClose: () => void;
}

/** Renders the optional rename dialog without adding another branch to the page. */
export function RenameRequestDialog({
  request,
  onClose,
}: RenameRequestDialogProps) {
  if (!request) {
    return null;
  }
  return (
    <RenameFileDialog
      key={request.file_id}
      file={request}
      onClose={onClose}
      onRenamed={onClose}
    />
  );
}

interface FolderDialogSlotsProps {
  readonly renameRequest: DirectorySchema | null;
  readonly moveCopyRequest: FolderMoveCopyRequest | null;
  readonly deleteRequest: DirectorySchema | null;
  readonly currentPath: string;
  readonly onCloseRename: () => void;
  readonly onRenamed: (result: FolderMutationSchema) => void;
  readonly onCloseMoveCopy: () => void;
  readonly onMoveCopyDone: (
    result: FolderMutationSchema,
    mode: FileOperationMode,
  ) => void;
  readonly onCloseDelete: () => void;
  readonly onDeleted: (result: LibraryDeleteResultSchema) => void;
}

/** Renders the folder rename, move/copy, and delete dialogs outside the page body. */
export function FolderDialogSlots({
  renameRequest,
  moveCopyRequest,
  deleteRequest,
  currentPath,
  onCloseRename,
  onRenamed,
  onCloseMoveCopy,
  onMoveCopyDone,
  onCloseDelete,
  onDeleted,
}: FolderDialogSlotsProps) {
  return (
    <>
      {renameRequest ? (
        <RenameFolderDialog
          key={renameRequest.path}
          folder={renameRequest}
          onClose={onCloseRename}
          onRenamed={onRenamed}
        />
      ) : null}

      {moveCopyRequest ? (
        <MoveCopyFolderDialog
          key={`${moveCopyRequest.mode}:${moveCopyRequest.folder.path}`}
          folder={moveCopyRequest.folder}
          mode={moveCopyRequest.mode}
          currentPath={currentPath}
          onClose={onCloseMoveCopy}
          onDone={onMoveCopyDone}
        />
      ) : null}

      {deleteRequest ? (
        <DeleteFolderDialog
          key={deleteRequest.path}
          folder={deleteRequest}
          onClose={onCloseDelete}
          onDeleted={onDeleted}
        />
      ) : null}
    </>
  );
}

interface DeleteSelectionDialogRequestProps {
  readonly request: DeleteSelectionRequest | null;
  readonly onClose: () => void;
  readonly onDeleted: (result: LibraryDeleteResultSchema) => void;
}

/** Renders the batch-delete dialog without adding another branch to the page. */
export function DeleteSelectionDialogRequest({
  request,
  onClose,
  onDeleted,
}: DeleteSelectionDialogRequestProps) {
  if (!request) {
    return null;
  }
  return (
    <DeleteSelectionDialog
      files={request.files}
      folders={request.folders}
      onClose={onClose}
      onDeleted={onDeleted}
    />
  );
}

interface LibrarySelectionBarSlotProps {
  readonly tab: LibraryTab;
  readonly selecting: boolean;
  readonly selectedFileCount: number;
  readonly selectedFolderCount: number;
  readonly visibleCount: number;
  readonly onSelectAll: () => void;
  readonly onClear: () => void;
  readonly onMoveSelected: () => void;
  readonly onDeleteSelected: () => void;
  readonly onExit: () => void;
}

/** Renders the Files-tab selection bar without branching in the page body. */
export function LibrarySelectionBarSlot({
  tab,
  selecting,
  ...barProps
}: LibrarySelectionBarSlotProps) {
  if (tab !== "files" || !selecting) {
    return null;
  }
  return <LibrarySelectionBar {...barProps} />;
}
