import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";

interface LibraryEmptyStateProps {
  readonly path: string;
  readonly query: string;
  readonly seeding: boolean;
  readonly onUpload: () => void;
  readonly onNewFolder: () => void;
  readonly onClearSearch: () => void;
  readonly onOpenRoot: () => void;
  readonly onSeed: () => void;
}

/** Empty, first-run, and no-match states for the Files tab. */
export function LibraryEmptyState({
  path,
  query,
  seeding,
  onUpload,
  onNewFolder,
  onClearSearch,
  onOpenRoot,
  onSeed,
}: LibraryEmptyStateProps) {
  if (query) {
    return (
      <EmptyState
        icon="search"
        eyebrow="Fuzzy path search"
        title={`No paths match “${query}”.`}
        description="Try fewer characters or another fragment of the path. Search is scoped to the folder in the breadcrumb."
        className="library-empty"
        action={
          <Button variant="secondary" size="sm" onClick={onClearSearch}>
            Clear search
          </Button>
        }
      />
    );
  }

  const isRoot = path === "/";
  return (
    <EmptyState
      icon={isRoot ? "library" : "folder"}
      eyebrow={isRoot ? "First run · empty archive" : "Empty folder"}
      title={isRoot ? "The shelf is ready for its first leaf." : "No files in this folder yet."}
      description={
        isRoot
          ? "Upload a file, write a text note, or drop files anywhere in the workspace. Every path becomes a branch and later versions keep their history."
          : `Drop files anywhere in this workspace to archive them in ${path}, or create a folder branch. Parent folders are created automatically.`
      }
      className="library-empty"
      aside={
        <span className="library-dropzone__hint">
          <Icon name="arrow-down" size={14} />
          Drop zone · 10 MB per file · allowed archive types
        </span>
      }
      action={
        <div className="empty-state__actions">
          <Button variant="ink" size="sm" onClick={onUpload}>
            <Icon name="plus" size={15} />
            Upload a file
          </Button>
          <Button variant="secondary" size="sm" onClick={onNewFolder}>
            <Icon name="folder" size={15} />
            New folder
          </Button>
          {isRoot ? (
            <Button variant="ghost" size="sm" onClick={onSeed} disabled={seeding} aria-busy={seeding}>
              {seeding ? "Seeding demo archive…" : "Seed demo archive"}
              {seeding ? null : <Icon name="spark" size={15} />}
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={onOpenRoot}>
              Back to archive root
            </Button>
          )}
        </div>
      }
    />
  );
}
