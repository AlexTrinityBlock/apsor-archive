import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type DragEvent,
} from "react";

import type {
  DirectorySchema,
  PathFileSchema,
  PathListingSchema,
} from "../../generated-apis-types/schemas";
import {
  basename,
  formatBytes,
  formatDateTime,
  formatNumber,
  parentPath,
  pathSegments,
} from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";
import {
  fileKindLabel,
  sameArchivePath,
  type LibraryUploadTask,
} from "./library-utils";

const INTERNAL_DRAG_MIME = "application/x-dendromatrix-file";

type FileOperationMode = "move" | "copy";
type DragKind = "file" | "external";

function resolveDragKind(
  event: DragEvent<HTMLElement>,
  hasInternalDrag: boolean,
): DragKind | null {
  const types = Array.from(event.dataTransfer.types);
  if (hasInternalDrag || types.includes(INTERNAL_DRAG_MIME)) {
    return "file";
  }
  if (types.includes("Files")) {
    return "external";
  }
  return null;
}

function canDropInto(
  kind: DragKind,
  dragFile: PathFileSchema | null,
  targetPath: string,
): boolean {
  if (kind === "external") {
    return true;
  }
  if (dragFile === null) {
    return false;
  }
  return !sameArchivePath(parentPath(dragFile.raw_file_path), targetPath);
}

function dropEffectFor(
  kind: DragKind,
  allowed: boolean,
  altKey: boolean,
): "copy" | "move" | "none" {
  if (kind === "external") {
    return "copy";
  }
  if (!allowed) {
    return "none";
  }
  return altKey ? "copy" : "move";
}

function dropHintFor(
  targetPath: string,
  activeTarget: string | null,
  allowed: boolean,
  external: boolean,
  copy: boolean,
): string | null {
  if (activeTarget !== targetPath) {
    return null;
  }
  if (!allowed) {
    return "Current folder";
  }
  if (external) {
    return "Drop to upload here";
  }
  return copy ? "Drop to copy here" : "Drop to move here";
}

interface DropHandlers {
  readonly onDragOver: (event: DragEvent<HTMLElement>, targetPath: string) => void;
  readonly onDragLeave: (event: DragEvent<HTMLElement>, targetPath: string) => void;
  readonly onDrop: (event: DragEvent<HTMLElement>, targetPath: string) => void;
}

interface FileCardProps {
  readonly file: PathFileSchema;
  readonly dragging: boolean;
  readonly menuOpen: boolean;
  readonly onOpen: (fileId: number) => void;
  readonly onToggleMenu: (fileId: number | null) => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onDragStart: (event: DragEvent<HTMLElement>, file: PathFileSchema) => void;
  readonly onDragEnd: () => void;
}

interface FolderCardProps extends DropHandlers {
  readonly folder: DirectorySchema;
  readonly dropLabel: string | null;
  readonly dropAllowed: boolean;
  readonly onOpenFolder: (path: string) => void;
  readonly onUploadHere: (path: string) => void;
}

interface FolderRailProps extends DropHandlers {
  readonly path: string;
  readonly directories: readonly DirectorySchema[];
  readonly dropTarget: string | null;
  readonly dropAllowed: boolean;
  readonly dropLabelFor: (targetPath: string) => string | null;
  readonly onOpenFolder: (path: string) => void;
}

interface UploadTrayProps {
  readonly tasks: readonly LibraryUploadTask[];
  readonly onDismiss: () => void;
}

interface EmptyBoardProps {
  readonly path: string;
  readonly query: string;
  readonly seeding: boolean;
  readonly onUpload: () => void;
  readonly onNewFolder: () => void;
  readonly onOpenRoot: () => void;
  readonly onClearSearch: () => void;
  readonly onSeed: () => void;
}

export interface LibraryBoardProps {
  readonly listing: PathListingSchema;
  readonly path: string;
  readonly query: string;
  readonly seeding: boolean;
  readonly uploads: readonly LibraryUploadTask[];
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number) => void;
  readonly onUpload: () => void;
  readonly onUploadHere: (folderPath: string) => void;
  readonly onNewFolder: () => void;
  readonly onClearSearch: () => void;
  readonly onSeed: () => void;
  readonly onDismissUploads: () => void;
  readonly onMoveFile: (file: PathFileSchema, targetFolder: string, mode: FileOperationMode) => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onFilesDropped: (files: readonly File[], targetFolder: string) => void;
}

function fileTone(rawPath: string): "image" | "document" | "text" {
  const kind = fileKindLabel(rawPath).toLowerCase();
  if (kind === "JPG" || kind === "JPEG" || kind === "PNG" || kind === "WEBP") {
    return "image";
  }
  if (kind === "PDF" || kind === "DOCX") {
    return "document";
  }
  return "text";
}

function uploadStatusLabel(task: LibraryUploadTask): string {
  if (task.status === "queued") {
    return "Queued";
  }
  if (task.status === "uploading") {
    return "Uploading";
  }
  if (task.status === "done") {
    return "Archived";
  }
  return "Rejected";
}

function FileCard({
  file,
  dragging,
  menuOpen,
  onOpen,
  onToggleMenu,
  onRequestMove,
  onDragStart,
  onDragEnd,
}: FileCardProps) {
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onToggleMenu(null);
        triggerRef.current?.focus();
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
        return;
      }
      const items = Array.from(
        menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [],
      );
      if (items.length === 0) {
        return;
      }
      event.preventDefault();
      const currentIndex = items.findIndex((item) => item === document.activeElement);
      const direction = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex =
        currentIndex < 0
          ? 0
          : (currentIndex + direction + items.length) % items.length;
      items[nextIndex].focus();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [menuOpen, onToggleMenu]);

  const classes = [
    "library-card",
    "library-file-card",
    dragging ? "is-dragging" : null,
    menuOpen ? "has-open-menu" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={classes}
      draggable
      data-library-file-id={file.file_id}
      onDragStart={(event) => onDragStart(event, file)}
      onDragEnd={onDragEnd}
      title="Drag onto a folder to move · hold Alt to copy"
    >
      <div className="library-card__top">
        <span
          className={`library-card__icon library-card__icon--${fileTone(file.raw_file_path)}`}
          aria-hidden="true"
        >
          <Icon name="file" size={19} />
        </span>
        <div className="library-card__identity">
          <button
            type="button"
            className="library-card__name"
            onClick={() => onOpen(file.file_id)}
          >
            {file.file_name}
          </button>
          <code className="library-card__path">{file.raw_file_path}</code>
        </div>
        <button
          ref={triggerRef}
          type="button"
          className="library-card__menu-trigger"
          data-library-menu-trigger={file.file_id}
          aria-label={`Actions for ${file.file_name}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? menuId : undefined}
          onClick={() => onToggleMenu(menuOpen ? null : file.file_id)}
        >
          <Icon name="settings" size={15} />
        </button>
      </div>

      <dl className="library-card__meta">
        <div>
          <dt>Kind</dt>
          <dd>{fileKindLabel(file.raw_file_path)}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{formatBytes(file.size_bytes)}</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>{formatNumber(file.total_chunks)}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>
            <time dateTime={file.update_time}>{formatDateTime(file.update_time)}</time>
          </dd>
        </div>
      </dl>

      <div className="library-card__foot">
        <Badge tone="moss" dot>
          Current leaf
        </Badge>
        <span className="library-card__drag-note">Drag to a branch</span>
      </div>

      {menuOpen ? (
        <div
          ref={menuRef}
          id={menuId}
          className="library-card__menu"
          role="menu"
          aria-label={`Move or copy ${file.file_name}`}
          data-library-file-menu
        >
          <button
            type="button"
            role="menuitem"
            className="library-card__menu-item"
            onClick={() => {
              onToggleMenu(null);
              onRequestMove(file, "move");
            }}
          >
            <Icon name="branch" size={15} />
            <span>
              Move to…
              <small>Keep the same file id and version.</small>
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-card__menu-item"
            onClick={() => {
              onToggleMenu(null);
              onRequestMove(file, "copy");
            }}
          >
            <Icon name="copy" size={15} />
            <span>
              Copy to…
              <small>Create a new leaf with fresh chunks.</small>
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-card__menu-item"
            onClick={() => {
              onToggleMenu(null);
              onOpen(file.file_id);
            }}
          >
            <Icon name="leaf" size={15} />
            <span>Open reader</span>
          </button>
        </div>
      ) : null}
    </article>
  );
}

function FolderCard({
  folder,
  dropLabel,
  dropAllowed,
  onDragOver,
  onDragLeave,
  onDrop,
  onOpenFolder,
  onUploadHere,
}: FolderCardProps) {
  const classes = [
    "library-card",
    "library-folder-card",
    dropLabel ? "is-drop-target" : null,
    dropLabel && !dropAllowed ? "is-drop-blocked" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article
      className={classes}
      onDragOver={(event) => onDragOver(event, folder.path)}
      onDragLeave={(event) => onDragLeave(event, folder.path)}
      onDrop={(event) => onDrop(event, folder.path)}
    >
      <button
        type="button"
        className="library-folder-card__open"
        onClick={() => onOpenFolder(folder.path)}
      >
        <span className="library-card__icon library-card__icon--folder" aria-hidden="true">
          <Icon name="folder" size={19} />
        </span>
        <span className="library-card__identity">
          <span className="library-card__name">{folder.name}</span>
          <code className="library-card__path">{folder.path}</code>
        </span>
        <Icon name="chevron-right" size={15} className="library-folder-card__chevron" />
      </button>

      <dl className="library-card__meta">
        <div>
          <dt>Kind</dt>
          <dd>Folder</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>—</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>—</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>—</dd>
        </div>
      </dl>

      <div className="library-card__foot">
        <Badge tone="neutral">Branch · depth {folder.depth}</Badge>
        <Button variant="ghost" size="sm" onClick={() => onUploadHere(folder.path)}>
          <Icon name="plus" size={13} />
          Upload here
        </Button>
      </div>

      {dropLabel ? <span className="library-card__drop-label">{dropLabel}</span> : null}
    </article>
  );
}

function FolderRail({
  path,
  directories,
  dropTarget,
  dropAllowed,
  dropLabelFor,
  onOpenFolder,
  onDragOver,
  onDragLeave,
  onDrop,
}: FolderRailProps) {
  const segments = pathSegments(path);
  const ancestors = [
    { name: "Archive", path: "/" },
    ...segments.map((segment, index) => ({
      name: segment,
      path: `/${segments.slice(0, index + 1).join("/")}`,
    })),
  ];

  return (
    <aside className="library-rail" aria-label="Folder tree">
      <div className="library-rail__head">
        <p className="eyebrow">Branch map</p>
        <h2 className="library-rail__title">{basename(path) || "Archive root"}</h2>
      </div>

      <nav className="library-rail__nav" aria-label="Folder ancestors">
        <ol className="library-rail__list">
          {ancestors.map((ancestor, index) => {
            const current = sameArchivePath(ancestor.path, path);
            const isTarget = dropTarget === ancestor.path;
            return (
              <li key={ancestor.path}>
                <button
                  type="button"
                  className={[
                    "library-rail__row",
                    current ? "is-current" : null,
                    isTarget ? "is-drop-target" : null,
                    isTarget && !dropAllowed ? "is-drop-blocked" : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  style={{ "--branch-depth": index } as CSSProperties}
                  aria-current={current ? "page" : undefined}
                  onClick={() => onOpenFolder(ancestor.path)}
                  onDragOver={(event) => onDragOver(event, ancestor.path)}
                  onDragLeave={(event) => onDragLeave(event, ancestor.path)}
                  onDrop={(event) => onDrop(event, ancestor.path)}
                >
                  <Icon name={index === 0 ? "library" : "folder"} size={14} />
                  <span className="library-rail__label">{ancestor.name}</span>
                  {isTarget ? (
                    <span className="library-rail__drop">{dropLabelFor(ancestor.path)}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      {directories.length > 0 ? (
        <div className="library-rail__children">
          <p className="eyebrow">Inner branches</p>
          <ul>
            {directories.map((folder) => {
              const isTarget = dropTarget === folder.path;
              return (
                <li key={folder.path}>
                  <button
                    type="button"
                    className={[
                      "library-rail__row",
                      "library-rail__row--child",
                      isTarget ? "is-drop-target" : null,
                      isTarget && !dropAllowed ? "is-drop-blocked" : null,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => onOpenFolder(folder.path)}
                    onDragOver={(event) => onDragOver(event, folder.path)}
                    onDragLeave={(event) => onDragLeave(event, folder.path)}
                    onDrop={(event) => onDrop(event, folder.path)}
                  >
                    <Icon name="folder" size={13} />
                    <span className="library-rail__label">{folder.name}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      <p className="library-rail__note">
        Drop a leaf on a branch to move it. Hold <kbd>Alt</kbd> while dropping to copy.
      </p>
    </aside>
  );
}

function UploadTaskMark({ task }: { readonly task: LibraryUploadTask }) {
  if (task.status === "done") {
    return (
      <span className="library-upload-task__mark" aria-hidden="true">
        <Icon name="check" size={13} />
      </span>
    );
  }
  if (task.status === "error") {
    return (
      <span className="library-upload-task__mark" aria-hidden="true">
        <Icon name="info" size={13} />
      </span>
    );
  }
  return (
    <span className="library-upload-task__mark" aria-hidden="true">
      <span className="library-upload-task__spinner" />
    </span>
  );
}

function UploadTray({ tasks, onDismiss }: UploadTrayProps) {
  if (tasks.length === 0) {
    return null;
  }
  const active = tasks.some(
    (task) => task.status === "queued" || task.status === "uploading",
  );
  const finished = tasks.filter((task) => task.status === "done").length;

  return (
    <section className="library-upload-tray" aria-live="polite" aria-busy={active}>
      <header className="library-upload-tray__head">
        <div>
          <p className="eyebrow">Intake queue</p>
          <span className="library-upload-tray__count">
            {finished}/{tasks.length} archived
          </span>
        </div>
        {active ? (
          <span className="library-upload-tray__busy">Uploading sequentially…</span>
        ) : (
          <Button variant="ghost" size="sm" onClick={onDismiss}>
            Clear tray
          </Button>
        )}
      </header>
      <ul className="library-upload-tray__list">
        {tasks.map((task) => (
          <li className={`library-upload-task is-${task.status}`} key={task.id}>
            <UploadTaskMark task={task} />
            <span className="library-upload-task__body">
              <span className="library-upload-task__name">{task.name}</span>
              <code className="library-upload-task__path">{task.targetPath}</code>
              {task.message ? (
                <span className="library-upload-task__message">{task.message}</span>
              ) : null}
            </span>
            <span className="library-upload-task__status">{uploadStatusLabel(task)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EmptyBoard({
  path,
  query,
  seeding,
  onUpload,
  onNewFolder,
  onOpenRoot,
  onClearSearch,
  onSeed,
}: EmptyBoardProps) {
  if (query) {
    return (
      <EmptyState
        icon="search"
        eyebrow="Fuzzy path search"
        title={`No paths match “${query}”.`}
        description="Try fewer characters or another fragment of the path. Search is scoped to the folder shown in the breadcrumb."
        className="library-board__empty reveal reveal-3"
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
      eyebrow={isRoot ? "First run · empty archive" : "Empty branch"}
      title={isRoot ? "The shelf is ready for its first leaf." : "No leaves in this folder yet."}
      description={
        isRoot
          ? "Drop files anywhere in this board, upload with the intake desk, or seed the demo archive. Every path becomes a branch and later versions keep their history."
          : `Drop files anywhere in this board to archive them in ${path}, or create a new branch folder. Parent folders are created automatically.`
      }
      className="library-board__empty reveal reveal-3"
      aside={
        <span className="library-dropzone__hint">
          <Icon name="arrow-down" size={14} />
          Drop zone · 10 MB per file · allowed archive types only
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

interface BoardHeaderProps {
  readonly query: string;
  readonly currentName: string;
  readonly path: string;
  readonly onClearSearch: () => void;
  readonly onNewFolder: () => void;
  readonly onUpload: () => void;
}

function BoardHeader({
  query,
  currentName,
  path,
  onClearSearch,
  onNewFolder,
  onUpload,
}: BoardHeaderProps) {
  return (
    <header className="library-board__head">
      <div className="library-board__heading">
        <p className="eyebrow">{query ? "Fuzzy path search" : "Folder workspace"}</p>
        <h2 className="library-board__title">
          {query ? `Matching “${query}”` : currentName}
        </h2>
        <code className="library-board__path">{path}</code>
      </div>
      <div className="library-board__actions">
        {query ? (
          <Button variant="secondary" size="sm" onClick={onClearSearch}>
            <Icon name="close" size={14} />
            Clear search
          </Button>
        ) : null}
        <Button variant="secondary" size="sm" onClick={onNewFolder}>
          <Icon name="folder" size={14} />
          New folder
        </Button>
        <Button variant="primary" size="sm" onClick={onUpload}>
          <Icon name="plus" size={14} />
          Add file
        </Button>
      </div>
    </header>
  );
}

interface BoardDragBarProps {
  readonly dragFile: PathFileSchema | null;
  readonly externalDrag: boolean;
  readonly dropTarget: string | null;
  readonly dropAllowed: boolean;
  readonly dropLabelFor: (targetPath: string) => string | null;
}

function BoardDragBar({
  dragFile,
  externalDrag,
  dropTarget,
  dropAllowed,
  dropLabelFor,
}: BoardDragBarProps) {
  if (!dragFile && !externalDrag) {
    return null;
  }
  const hint =
    dropTarget !== null ? dropLabelFor(dropTarget) : "Drop to move · Alt-drop to copy";
  return (
    <div
      className={[
        "library-dragbar",
        dropTarget !== null && !dropAllowed ? "is-blocked" : null,
      ]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-live="polite"
    >
      <Icon name={dragFile ? "leaf" : "arrow-down"} size={15} />
      <span className="library-dragbar__label">
        {dragFile ? `“${dragFile.file_name}”` : "Incoming files"}
      </span>
      <span className="library-dragbar__hint">{hint}</span>
    </div>
  );
}

interface BoardSectionsProps {
  readonly listing: PathListingSchema;
  readonly path: string;
  readonly query: string;
  readonly seeding: boolean;
  readonly uploads: readonly LibraryUploadTask[];
  readonly dragFile: PathFileSchema | null;
  readonly menuFileId: number | null;
  readonly dropAllowed: boolean;
  readonly dropHandlers: DropHandlers;
  readonly dropLabelFor: (targetPath: string) => string | null;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number) => void;
  readonly onUpload: () => void;
  readonly onUploadHere: (path: string) => void;
  readonly onNewFolder: () => void;
  readonly onClearSearch: () => void;
  readonly onSeed: () => void;
  readonly onDismissUploads: () => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onFileDragStart: (event: DragEvent<HTMLElement>, file: PathFileSchema) => void;
  readonly onResetDrag: () => void;
  readonly onToggleMenu: (fileId: number | null) => void;
}

function BoardSections({
  listing,
  path,
  query,
  seeding,
  uploads,
  dragFile,
  menuFileId,
  dropAllowed,
  dropHandlers,
  dropLabelFor,
  onOpenFolder,
  onOpenFile,
  onUpload,
  onUploadHere,
  onNewFolder,
  onClearSearch,
  onSeed,
  onDismissUploads,
  onRequestMove,
  onFileDragStart,
  onResetDrag,
  onToggleMenu,
}: BoardSectionsProps) {
  const folderCount = query ? 0 : listing.directories.length;
  const fileCount = listing.files.length;
  const entryCount = folderCount + fileCount;

  return (
    <>
      <UploadTray tasks={uploads} onDismiss={onDismissUploads} />

      {entryCount === 0 ? (
        <EmptyBoard
          path={path}
          query={query}
          seeding={seeding}
          onUpload={onUpload}
          onNewFolder={onNewFolder}
          onOpenRoot={() => onOpenFolder("/")}
          onClearSearch={onClearSearch}
          onSeed={onSeed}
        />
      ) : (
        <div className="library-board__sections">
          {folderCount > 0 ? (
            <section className="library-board__section" aria-labelledby="library-folders-heading">
              <div className="library-board__section-head">
                <h3 id="library-folders-heading">Folders</h3>
                <Badge tone="neutral">
                  {folderCount} {folderCount === 1 ? "branch" : "branches"}
                </Badge>
                <span className="library-board__section-hint">
                  Drop files or leaves onto a branch
                </span>
              </div>
              <div className="library-board__grid library-board__grid--folders">
                {listing.directories.map((folder) => (
                  <FolderCard
                    key={folder.path}
                    folder={folder}
                    dropLabel={dropLabelFor(folder.path)}
                    dropAllowed={dropAllowed}
                    onOpenFolder={onOpenFolder}
                    onUploadHere={onUploadHere}
                    {...dropHandlers}
                  />
                ))}
              </div>
            </section>
          ) : null}

          {fileCount > 0 ? (
            <section className="library-board__section" aria-labelledby="library-files-heading">
              <div className="library-board__section-head">
                <h3 id="library-files-heading">
                  {query ? "Matching leaves" : "Leaves"}
                </h3>
                <Badge tone={query ? "ochre" : "moss"}>
                  {fileCount} {fileCount === 1 ? "file" : "files"}
                </Badge>
                <span className="library-board__section-hint">
                  {query ? "Paths matching the current search" : "Drag a leaf to move it"}
                </span>
              </div>
              <div className="library-board__grid library-board__grid--files">
                {listing.files.map((file) => (
                  <FileCard
                    key={file.file_id}
                    file={file}
                    dragging={dragFile?.file_id === file.file_id}
                    menuOpen={menuFileId === file.file_id}
                    onOpen={onOpenFile}
                    onToggleMenu={onToggleMenu}
                    onRequestMove={onRequestMove}
                    onDragStart={onFileDragStart}
                    onDragEnd={onResetDrag}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </>
  );
}

/**
 * The folder-first shelf. Board cards share the archive's paper/moss language,
 * folder cards double as drop targets, and the whole board is the current
 * folder's drop zone. Every drag action also has a menu path for touch users.
 */
export function LibraryBoard({
  listing,
  path,
  query,
  seeding,
  uploads,
  onOpenFolder,
  onOpenFile,
  onUpload,
  onUploadHere,
  onNewFolder,
  onClearSearch,
  onSeed,
  onDismissUploads,
  onMoveFile,
  onRequestMove,
  onFilesDropped,
}: LibraryBoardProps) {
  const [dragFile, setDragFile] = useState<PathFileSchema | null>(null);
  const [externalDrag, setExternalDrag] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [dropAllowed, setDropAllowed] = useState(true);
  const [copyIntent, setCopyIntent] = useState(false);
  const [menuFileId, setMenuFileId] = useState<number | null>(null);

  const resetDrag = useCallback(() => {
    setDragFile(null);
    setExternalDrag(false);
    setDropTarget(null);
    setDropAllowed(true);
    setCopyIntent(false);
  }, []);

  useEffect(() => {
    window.addEventListener("dragend", resetDrag);
    window.addEventListener("blur", resetDrag);
    return () => {
      window.removeEventListener("dragend", resetDrag);
      window.removeEventListener("blur", resetDrag);
    };
  }, [resetDrag]);

  useEffect(() => {
    if (menuFileId === null) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        setMenuFileId(null);
        return;
      }
      if (target.closest("[data-library-file-menu]")) {
        return;
      }
      if (target.closest(`[data-library-menu-trigger="${menuFileId}"]`)) {
        return;
      }
      setMenuFileId(null);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [menuFileId]);

  const handleFileDragStart = useCallback(
    (event: DragEvent<HTMLElement>, file: PathFileSchema) => {
      event.dataTransfer.setData(
        INTERNAL_DRAG_MIME,
        JSON.stringify({ fileId: file.file_id, rawPath: file.raw_file_path }),
      );
      event.dataTransfer.setData("text/plain", file.raw_file_path);
      event.dataTransfer.effectAllowed = "copyMove";
      setDragFile(file);
      setMenuFileId(null);
    },
    [],
  );

  const handleDragOver = useCallback(
    (event: DragEvent<HTMLElement>, targetPath: string) => {
      const kind = resolveDragKind(event, dragFile !== null);
      if (kind === null) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const allowed = canDropInto(kind, dragFile, targetPath);
      event.dataTransfer.dropEffect = dropEffectFor(kind, allowed, event.altKey);
      setExternalDrag(kind === "external");
      setDropTarget(targetPath);
      setDropAllowed(allowed);
      setCopyIntent(kind === "file" && allowed && event.altKey);
    },
    [dragFile],
  );

  const handleDragLeave = useCallback(
    (event: DragEvent<HTMLElement>, targetPath: string) => {
      const related = event.relatedTarget;
      if (related instanceof Node && event.currentTarget.contains(related)) {
        return;
      }
      setDropTarget((current) => (current === targetPath ? null : current));
    },
    [],
  );

  const handleDrop = useCallback(
    (event: DragEvent<HTMLElement>, targetPath: string) => {
      event.preventDefault();
      event.stopPropagation();
      const droppedFiles = Array.from(event.dataTransfer.files);
      const internal = dragFile !== null;
      const copy = event.altKey;
      const source = dragFile;
      resetDrag();

      if (internal && source) {
        if (sameArchivePath(parentPath(source.raw_file_path), targetPath)) {
          return;
        }
        onMoveFile(source, targetPath, copy ? "copy" : "move");
        return;
      }
      if (droppedFiles.length > 0) {
        onFilesDropped(droppedFiles, targetPath);
      }
    },
    [dragFile, onFilesDropped, onMoveFile, resetDrag],
  );

  const dropHandlers: DropHandlers = {
    onDragOver: handleDragOver,
    onDragLeave: handleDragLeave,
    onDrop: handleDrop,
  };

  const dropLabelFor = (targetPath: string): string | null =>
    dropHintFor(targetPath, dropTarget, dropAllowed, externalDrag, copyIntent);

  const boardClasses = [
    "library-board",
    dropTarget === path ? "is-drop-active" : null,
    dropTarget === path && !dropAllowed ? "is-drop-blocked" : null,
    externalDrag || dragFile ? "is-dragging" : null,
  ]
    .filter(Boolean)
    .join(" ");

  const currentName = basename(path) || "Archive root";

  return (
    <div className="library-workspace">
      <FolderRail
        path={path}
        directories={query ? [] : listing.directories}
        dropTarget={dropTarget}
        dropAllowed={dropAllowed}
        dropLabelFor={dropLabelFor}
        onOpenFolder={onOpenFolder}
        {...dropHandlers}
      />

      <section
        className={boardClasses}
        aria-label={`Folder workspace at ${path}`}
        onDragOver={(event) => handleDragOver(event, path)}
        onDragLeave={(event) => handleDragLeave(event, path)}
        onDrop={(event) => handleDrop(event, path)}
      >
        <BoardHeader
          query={query}
          currentName={currentName}
          path={path}
          onClearSearch={onClearSearch}
          onNewFolder={onNewFolder}
          onUpload={onUpload}
        />

        <BoardDragBar
          dragFile={dragFile}
          externalDrag={externalDrag}
          dropTarget={dropTarget}
          dropAllowed={dropAllowed}
          dropLabelFor={dropLabelFor}
        />

        <BoardSections
          listing={listing}
          path={path}
          query={query}
          seeding={seeding}
          uploads={uploads}
          dragFile={dragFile}
          menuFileId={menuFileId}
          dropAllowed={dropAllowed}
          dropHandlers={dropHandlers}
          dropLabelFor={dropLabelFor}
          onOpenFolder={onOpenFolder}
          onOpenFile={onOpenFile}
          onUpload={onUpload}
          onUploadHere={onUploadHere}
          onNewFolder={onNewFolder}
          onClearSearch={onClearSearch}
          onSeed={onSeed}
          onDismissUploads={onDismissUploads}
          onRequestMove={onRequestMove}
          onFileDragStart={handleFileDragStart}
          onResetDrag={resetDrag}
          onToggleMenu={setMenuFileId}
        />

        <footer className="library-board__footer">
          <span>
            <Icon name="arrow-down" size={13} />
            Drop files here to upload · 10 MB each
          </span>
          <span className="library-board__footer-note">
            Drop to move · <kbd>Alt</kbd>-drop to copy · card menus for touch
          </span>
        </footer>
      </section>
    </div>
  );
}
