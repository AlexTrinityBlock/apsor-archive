import type { PathFileSchema, PathListingSchema } from "../../generated-apis-types/schemas";
import { LibraryBoard } from "./LibraryBoard";
import { LibraryEmptyState } from "./LibraryEmptyState";
import { LibraryResults } from "./LibraryResults";
import type { FileOperationMode, LibraryView } from "./library-utils";

interface LibraryFilesContentProps {
  readonly listing: PathListingSchema;
  readonly path: string;
  readonly query: string;
  readonly view: LibraryView;
  readonly seeding: boolean;
  readonly selecting: boolean;
  readonly selectedFileIds: ReadonlySet<number>;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number) => void;
  readonly onUpload: () => void;
  readonly onUploadHere: (path: string) => void;
  readonly onNewFolder: () => void;
  readonly onClearSearch: () => void;
  readonly onOpenRoot: () => void;
  readonly onSeed: () => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onRequestDelete: (file: PathFileSchema) => void;
  readonly onMoveFile: (
    file: PathFileSchema,
    targetFolder: string,
    mode: FileOperationMode,
  ) => void;
  readonly onFilesDropped: (files: readonly File[], targetFolder: string) => void;
}

/** Chooses the Files tab presentation without duplicating empty-state logic. */
export function LibraryFilesContent({
  listing,
  path,
  query,
  view,
  seeding,
  selecting,
  selectedFileIds,
  onToggleSelected,
  onOpenFolder,
  onOpenFile,
  onUpload,
  onUploadHere,
  onNewFolder,
  onClearSearch,
  onOpenRoot,
  onSeed,
  onRequestMove,
  onRequestDelete,
  onMoveFile,
  onFilesDropped,
}: LibraryFilesContentProps) {
  const entryCount = listing.directories.length + listing.files.length;

  if (entryCount === 0) {
    return (
      <LibraryBoard
        listing={listing}
        path={path}
        query={query}
        selecting={selecting}
        selectedFileIds={selectedFileIds}
        onToggleSelected={onToggleSelected}
        onOpenFolder={onOpenFolder}
        onOpenFile={onOpenFile}
        onUploadHere={onUploadHere}
        onRequestMove={onRequestMove}
        onRequestDelete={onRequestDelete}
        onMoveFile={onMoveFile}
        onFilesDropped={onFilesDropped}
        emptyState={
          <LibraryEmptyState
            path={path}
            query={query}
            seeding={seeding}
            onUpload={onUpload}
            onNewFolder={onNewFolder}
            onClearSearch={onClearSearch}
            onOpenRoot={onOpenRoot}
            onSeed={onSeed}
          />
        }
      />
    );
  }

  if (view === "list") {
    return (
      <LibraryResults
        listing={listing}
        query={query}
        selecting={selecting}
        selectedFileIds={selectedFileIds}
        onToggleSelected={onToggleSelected}
        onOpenFolder={onOpenFolder}
        onOpenFile={onOpenFile}
        onRequestMove={onRequestMove}
        onRequestDelete={onRequestDelete}
      />
    );
  }

  return (
    <LibraryBoard
      listing={listing}
      path={path}
      query={query}
      selecting={selecting}
      selectedFileIds={selectedFileIds}
      onToggleSelected={onToggleSelected}
      onOpenFolder={onOpenFolder}
      onOpenFile={onOpenFile}
      onUploadHere={onUploadHere}
      onRequestMove={onRequestMove}
      onRequestDelete={onRequestDelete}
      onMoveFile={onMoveFile}
      onFilesDropped={onFilesDropped}
    />
  );
}
