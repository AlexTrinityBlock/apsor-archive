import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

import type {
  DirectorySchema,
  PathFileSchema,
  PathListingSchema,
} from "../../generated-apis-types/schemas";
import { formatBytes, parentPath } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useI18n, type Translate } from "../../i18n";
import {
  contextMenuTriggerFromKeyboard,
  fileKindLabel,
  isContextMenuKey,
  isMarkdownFile,
  sameArchivePath,
  type FileOperationMode,
  type LibraryContextMenuTrigger,
} from "./library-utils";

const INTERNAL_DRAG_MIME = "application/x-apsor-archive-file";

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
  t: Translate,
): string | null {
  if (activeTarget !== targetPath) {
    return null;
  }
  if (!allowed) {
    return t("library.board.dropCurrentFolder");
  }
  if (external) {
    return t("library.board.dropUpload");
  }
  return copy ? t("library.board.dropCopy") : t("library.board.dropMove");
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
  readonly selecting: boolean;
  readonly selected: boolean;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onOpen: (fileId: number) => void;
  readonly onEditFile: (fileId: number) => void;
  readonly onFileContextMenu: (
    event: LibraryContextMenuTrigger,
    file: PathFileSchema,
  ) => void;
  readonly onToggleMenu: (fileId: number | null) => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onRequestDelete: (file: PathFileSchema) => void;
  readonly onDragStart: (event: DragEvent<HTMLElement>, file: PathFileSchema) => void;
  readonly onDragEnd: () => void;
}

interface CardMenuRefs {
  readonly triggerRef: RefObject<HTMLButtonElement | null>;
  readonly menuRef: RefObject<HTMLDivElement | null>;
}

/** Shared menu focus and keyboard behaviour for file and folder cards. */
function useCardMenu(menuOpen: boolean, onClose: () => void): CardMenuRefs {
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
        onClose();
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
        currentIndex < 0 ? 0 : (currentIndex + direction + items.length) % items.length;
      items[nextIndex].focus();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [menuOpen, onClose]);

  return { triggerRef, menuRef };
}

function FileCard({
  file,
  dragging,
  menuOpen,
  selecting,
  selected,
  onToggleSelected,
  onOpen,
  onEditFile,
  onFileContextMenu,
  onToggleMenu,
  onRequestMove,
  onRequestDelete,
  onDragStart,
  onDragEnd,
}: FileCardProps) {
  const { t, formatNumber, formatDateTime } = useI18n();
  const menuId = useId();
  const closeMenu = useCallback(() => onToggleMenu(null), [onToggleMenu]);
  const { triggerRef, menuRef } = useCardMenu(menuOpen, closeMenu);

  const handleContextMenuKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
  ) => {
    if (!isContextMenuKey(event)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    onFileContextMenu(contextMenuTriggerFromKeyboard(event.currentTarget), file);
  };

  const classes = [
    "library-file-card",
    dragging ? "is-dragging" : null,
    menuOpen ? "has-open-menu" : null,
    selected ? "is-selected" : null,
    selecting ? "is-selecting" : null,
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
      onContextMenu={(event) => onFileContextMenu(event, file)}
      tabIndex={-1}
      title={t("library.board.dragTitle")}
    >
      {selecting ? (
        <label className="library-checkbox library-file-card__check">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelected(file.file_id)}
            aria-label={t("library.a11y.selectFile", { name: file.file_name })}
          />
          <span className="library-checkbox__box" aria-hidden="true">
            <Icon name="check" size={12} />
          </span>
        </label>
      ) : null}

      <button
        type="button"
        className="library-file-card__open"
        onClick={() => onOpen(file.file_id)}
        onKeyDown={handleContextMenuKeyDown}
        aria-label={t("library.a11y.openPreviewOf", { name: file.file_name })}
      >
        <span className="library-file-card__top">
          <span className="file-type-pill">{fileKindLabel(file.raw_file_path)}</span>
          <Icon name="leaf" size={15} className="library-file-card__leaf" />
        </span>
        <span className="library-file-card__name">{file.file_name}</span>
        <code className="library-file-card__path">{file.raw_file_path}</code>
        <span className="library-file-card__meta">
          <span>
            {formatBytes(file.size_bytes)} ·{" "}
            {t(
              file.total_chunks === 1
                ? "library.units.chunkOne"
                : "library.units.chunkOther",
              { count: formatNumber(file.total_chunks) },
            )}
          </span>
          <time dateTime={file.update_time}>{formatDateTime(file.update_time)}</time>
        </span>
      </button>

      <button
        ref={triggerRef}
        type="button"
        className="library-file-card__menu-trigger"
        data-library-menu-trigger={file.file_id}
        aria-label={t("library.a11y.actionsFor", { name: file.file_name })}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-controls={menuOpen ? menuId : undefined}
        onClick={() => onToggleMenu(menuOpen ? null : file.file_id)}
      >
        <Icon name="settings" size={15} />
      </button>

      {menuOpen ? (
        <div
          ref={menuRef}
          id={menuId}
          className="library-file-menu"
          role="menu"
          aria-label={t("library.a11y.actionsFor", { name: file.file_name })}
          data-library-file-menu
        >
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => {
              onToggleMenu(null);
              onOpen(file.file_id);
            }}
          >
            <Icon name="file" size={15} />
            <span>{t("library.board.openPreview")}</span>
          </button>
          {isMarkdownFile(file.raw_file_path) ? (
            <button
              type="button"
              role="menuitem"
              className="library-file-menu__item"
              onClick={() => {
                onToggleMenu(null);
                onEditFile(file.file_id);
              }}
            >
              <Icon name="pencil" size={15} />
              <span>{t("library.editor.editFile")}</span>
            </button>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => {
              onToggleMenu(null);
              onRequestMove(file, "move");
            }}
          >
            <Icon name="branch" size={15} />
            <span>{t("library.board.moveTo")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => {
              onToggleMenu(null);
              onRequestMove(file, "copy");
            }}
          >
            <Icon name="copy" size={15} />
            <span>{t("library.board.copyTo")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item library-file-menu__item--danger"
            onClick={() => {
              onToggleMenu(null);
              onRequestDelete(file);
            }}
          >
            <Icon name="trash" size={15} />
            <span>{t("library.board.deleteFile")}</span>
          </button>
        </div>
      ) : null}
    </article>
  );
}

interface FolderCardProps extends DropHandlers {
  readonly folder: DirectorySchema;
  readonly dropLabel: string | null;
  readonly dropAllowed: boolean;
  readonly selecting: boolean;
  readonly selected: boolean;
  readonly menuOpen: boolean;
  readonly onToggleSelected: (path: string) => void;
  readonly onToggleMenu: (path: string | null) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onUploadHere: (path: string) => void;
  readonly onNewMarkdownHere: (path: string) => void;
  readonly onCopyPath: (path: string) => void;
  readonly onRequestRename: (folder: DirectorySchema) => void;
  readonly onRequestMoveCopy: (
    folder: DirectorySchema,
    mode: FileOperationMode,
  ) => void;
  readonly onRequestDelete: (folder: DirectorySchema) => void;
  readonly onFolderContextMenu: (
    event: LibraryContextMenuTrigger,
    folder: DirectorySchema,
  ) => void;
}

function FolderCard({
  folder,
  dropLabel,
  dropAllowed,
  selecting,
  selected,
  menuOpen,
  onToggleSelected,
  onToggleMenu,
  onDragOver,
  onDragLeave,
  onDrop,
  onOpenFolder,
  onUploadHere,
  onNewMarkdownHere,
  onCopyPath,
  onRequestRename,
  onRequestMoveCopy,
  onRequestDelete,
  onFolderContextMenu,
}: FolderCardProps) {
  const { t } = useI18n();
  const menuId = useId();
  const closeMenu = useCallback(() => onToggleMenu(null), [onToggleMenu]);
  const { triggerRef, menuRef } = useCardMenu(menuOpen, closeMenu);
  const classes = [
    "library-folder-card",
    dropLabel ? "is-drop-target" : null,
    dropLabel && !dropAllowed ? "is-drop-blocked" : null,
    menuOpen ? "has-open-menu" : null,
    selected ? "is-selected" : null,
    selecting ? "is-selecting" : null,
  ]
    .filter(Boolean)
    .join(" ");

  const runMenuAction = (action: () => void) => {
    onToggleMenu(null);
    action();
  };

  return (
    <article
      className={classes}
      onDragOver={(event) => onDragOver(event, folder.path)}
      onDragLeave={(event) => onDragLeave(event, folder.path)}
      onDrop={(event) => onDrop(event, folder.path)}
      onContextMenu={(event) => onFolderContextMenu(event, folder)}
      tabIndex={-1}
    >
      {selecting ? (
        <label className="library-checkbox library-folder-card__check">
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelected(folder.path)}
            aria-label={t("library.a11y.selectFolder", { name: folder.name })}
          />
          <span className="library-checkbox__box" aria-hidden="true">
            <Icon name="check" size={12} />
          </span>
        </label>
      ) : null}

      <button
        type="button"
        className="library-folder-card__open"
        onClick={() => onOpenFolder(folder.path)}
        onKeyDown={(event) => {
          if (!isContextMenuKey(event)) {
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          onFolderContextMenu(
            contextMenuTriggerFromKeyboard(event.currentTarget),
            folder,
          );
        }}
      >
        <span className="library-folder-card__icon" aria-hidden="true">
          <Icon name="folder" size={20} />
        </span>
        <span className="library-folder-card__copy">
          <span className="library-folder-card__name">{folder.name}</span>
          <code className="library-folder-card__path">{folder.path}</code>
        </span>
        <Icon name="chevron-right" size={15} className="library-folder-card__chevron" />
      </button>

      <button
        ref={triggerRef}
        type="button"
        className="library-file-card__menu-trigger library-folder-card__menu-trigger"
        data-library-folder-menu-trigger={folder.path}
        aria-label={t("library.a11y.actionsForFolder", { name: folder.name })}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-controls={menuOpen ? menuId : undefined}
        onClick={() => onToggleMenu(menuOpen ? null : folder.path)}
      >
        <Icon name="settings" size={15} />
      </button>

      {menuOpen ? (
        <div
          ref={menuRef}
          id={menuId}
          className="library-file-menu library-folder-menu"
          role="menu"
          aria-label={t("library.a11y.actionsForFolder", { name: folder.name })}
          data-library-folder-menu
        >
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onOpenFolder(folder.path))}
          >
            <Icon name="folder" size={15} />
            <span>{t("library.contextMenu.openFolder")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onNewMarkdownHere(folder.path))}
          >
            <Icon name="file" size={15} />
            <span>{t("library.contextMenu.newMarkdownHere")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onUploadHere(folder.path))}
          >
            <Icon name="plus" size={15} />
            <span>{t("library.contextMenu.uploadHere")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onRequestRename(folder))}
          >
            <Icon name="pencil" size={15} />
            <span>{t("library.board.renameFolder")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onRequestMoveCopy(folder, "move"))}
          >
            <Icon name="branch" size={15} />
            <span>{t("library.board.moveFolder")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onRequestMoveCopy(folder, "copy"))}
          >
            <Icon name="copy" size={15} />
            <span>{t("library.board.copyFolder")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item library-file-menu__item--danger"
            onClick={() => runMenuAction(() => onRequestDelete(folder))}
          >
            <Icon name="trash" size={15} />
            <span>{t("library.board.deleteFolder")}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="library-file-menu__item"
            onClick={() => runMenuAction(() => onCopyPath(folder.path))}
          >
            <Icon name="copy" size={15} />
            <span>{t("library.contextMenu.copyPath")}</span>
          </button>
        </div>
      ) : null}

      <div className="library-folder-card__foot">
        <span className="library-folder-card__depth">
          {t("library.board.branchDepth", { depth: folder.depth })}
        </span>
        <Button variant="ghost" size="sm" onClick={() => onUploadHere(folder.path)}>
          <Icon name="plus" size={13} />
          {t("library.board.uploadHere")}
        </Button>
      </div>
      {dropLabel ? <span className="library-folder-card__drop">{dropLabel}</span> : null}
    </article>
  );
}

interface LibraryBoardProps {
  readonly listing: PathListingSchema;
  readonly path: string;
  readonly query: string;
  readonly selecting: boolean;
  readonly selectedFileIds: ReadonlySet<number>;
  readonly selectedFolderPaths: ReadonlySet<string>;
  readonly onToggleSelected: (fileId: number) => void;
  readonly onToggleSelectedFolder: (path: string) => void;
  readonly onOpenFolder: (path: string) => void;
  readonly onOpenFile: (fileId: number) => void;
  readonly onEditFile: (fileId: number) => void;
  readonly onFileContextMenu: (
    event: LibraryContextMenuTrigger,
    file: PathFileSchema,
  ) => void;
  readonly onFolderContextMenu: (
    event: LibraryContextMenuTrigger,
    folder: DirectorySchema,
  ) => void;
  readonly onUploadHere: (path: string) => void;
  readonly onNewMarkdownHere: (path: string) => void;
  readonly onCopyPath: (path: string) => void;
  readonly onRequestRenameFolder: (folder: DirectorySchema) => void;
  readonly onRequestMoveCopyFolder: (
    folder: DirectorySchema,
    mode: FileOperationMode,
  ) => void;
  readonly onRequestDeleteFolder: (folder: DirectorySchema) => void;
  readonly onRequestMove: (file: PathFileSchema, mode: FileOperationMode) => void;
  readonly onRequestDelete: (file: PathFileSchema) => void;
  readonly onMoveFile: (
    file: PathFileSchema,
    targetFolder: string,
    mode: FileOperationMode,
  ) => void;
  readonly onFilesDropped: (files: readonly File[], targetFolder: string) => void;
  readonly emptyState?: ReactNode;
}

/**
 * The folder-first board. Folder cards are drop targets, the board itself
 * accepts drops into the current folder, and every drag action has a menu path
 * for touch and keyboard users.
 */
export function LibraryBoard({
  listing,
  path,
  query,
  selecting,
  selectedFileIds,
  selectedFolderPaths,
  onToggleSelected,
  onToggleSelectedFolder,
  onOpenFolder,
  onOpenFile,
  onEditFile,
  onFileContextMenu,
  onFolderContextMenu,
  onUploadHere,
  onNewMarkdownHere,
  onCopyPath,
  onRequestRenameFolder,
  onRequestMoveCopyFolder,
  onRequestDeleteFolder,
  onRequestMove,
  onRequestDelete,
  onMoveFile,
  onFilesDropped,
  emptyState = null,
}: LibraryBoardProps) {
  const { t, formatNumber } = useI18n();
  const [dragFile, setDragFile] = useState<PathFileSchema | null>(null);
  const [externalDrag, setExternalDrag] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [dropAllowed, setDropAllowed] = useState(true);
  const [copyIntent, setCopyIntent] = useState(false);
  const [menuFileId, setMenuFileId] = useState<number | null>(null);
  const [menuFolderPath, setMenuFolderPath] = useState<string | null>(null);

  const folders = query ? [] : listing.directories;
  const hasEntries = folders.length > 0 || listing.files.length > 0;

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
    if (menuFileId === null && menuFolderPath === null) {
      return;
    }
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        setMenuFileId(null);
        setMenuFolderPath(null);
        return;
      }
      if (
        target.closest("[data-library-file-menu]") ||
        target.closest("[data-library-folder-menu]")
      ) {
        return;
      }
      if (
        menuFileId !== null &&
        target.closest(`[data-library-menu-trigger="${menuFileId}"]`)
      ) {
        return;
      }
      if (
        menuFolderPath !== null &&
        target
          .closest("[data-library-folder-menu-trigger]")
          ?.getAttribute("data-library-folder-menu-trigger") === menuFolderPath
      ) {
        return;
      }
      setMenuFileId(null);
      setMenuFolderPath(null);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [menuFileId, menuFolderPath]);

  const handleToggleFileMenu = useCallback((fileId: number | null) => {
    setMenuFolderPath(null);
    setMenuFileId(fileId);
  }, []);

  const handleToggleFolderMenu = useCallback((folderPath: string | null) => {
    setMenuFileId(null);
    setMenuFolderPath(folderPath);
  }, []);

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
      setMenuFolderPath(null);
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
      const source = dragFile;
      const copy = event.altKey;
      resetDrag();

      if (source) {
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
    dropHintFor(targetPath, dropTarget, dropAllowed, externalDrag, copyIntent, t);

  const boardClasses = [
    "library-board",
    dropTarget === path ? "is-drop-active" : null,
    dropTarget === path && !dropAllowed ? "is-drop-blocked" : null,
  ]
    .filter(Boolean)
    .join(" ");

  let filesHint = t("library.board.filesHintDefault");
  if (query) {
    filesHint = t("library.board.filesHintQuery");
  } else if (selecting) {
    filesHint = t("library.board.filesHintSelecting");
  }

  return (
    <div className="library-board-wrap">
      <div
        className={boardClasses}
        aria-label={t("library.board.workspaceAria", { path })}
        onDragOver={(event) => handleDragOver(event, path)}
        onDragLeave={(event) => handleDragLeave(event, path)}
        onDrop={(event) => handleDrop(event, path)}
      >
        <BoardDragBar
          dragFile={dragFile}
          externalDrag={externalDrag}
          dropTarget={dropTarget}
          dropAllowed={dropAllowed}
          dropLabelFor={dropLabelFor}
        />

        {hasEntries ? (
          <>
            {folders.length > 0 ? (
              <section className="library-section" aria-labelledby="library-folders-heading">
                <div className="library-section__head">
                  <h2 id="library-folders-heading">{t("library.board.foldersHeading")}</h2>
                  <Badge tone="neutral">
                    {t(
                      folders.length === 1
                        ? "library.units.folderOne"
                        : "library.units.folderOther",
                      { count: formatNumber(folders.length) },
                    )}
                  </Badge>
                  <span className="library-section__hint">
                    {t("library.board.foldersHint")}
                  </span>
                </div>
                <div className="library-folder-grid">
                  {folders.map((folder) => (
                    <FolderCard
                      key={folder.path}
                      folder={folder}
                      dropLabel={dropLabelFor(folder.path)}
                      dropAllowed={dropAllowed}
                      selecting={selecting}
                      selected={selectedFolderPaths.has(folder.path)}
                      menuOpen={menuFolderPath === folder.path}
                      onToggleSelected={onToggleSelectedFolder}
                      onToggleMenu={handleToggleFolderMenu}
                      onOpenFolder={onOpenFolder}
                      onUploadHere={onUploadHere}
                      onNewMarkdownHere={onNewMarkdownHere}
                      onCopyPath={onCopyPath}
                      onRequestRename={onRequestRenameFolder}
                      onRequestMoveCopy={onRequestMoveCopyFolder}
                      onRequestDelete={onRequestDeleteFolder}
                      onFolderContextMenu={onFolderContextMenu}
                      {...dropHandlers}
                    />
                  ))}
                </div>
              </section>
            ) : null}

            {listing.files.length > 0 ? (
              <section className="library-section" aria-labelledby="library-files-heading">
                <div className="library-section__head">
                  <h2 id="library-files-heading">
                    {query
                      ? t("library.board.matchingFilesHeading")
                      : t("library.board.filesHeading")}
                  </h2>
                  <Badge tone={query ? "ochre" : "moss"}>
                    {t(
                      listing.files.length === 1
                        ? "library.units.fileOne"
                        : "library.units.fileOther",
                      { count: formatNumber(listing.files.length) },
                    )}
                  </Badge>
                  <span className="library-section__hint">{filesHint}</span>
                </div>
                <div className="library-file-grid">
                  {listing.files.map((file) => (
                    <FileCard
                      key={file.file_id}
                      file={file}
                      dragging={dragFile?.file_id === file.file_id}
                      menuOpen={menuFileId === file.file_id}
                      selecting={selecting}
                      selected={selectedFileIds.has(file.file_id)}
                      onToggleSelected={onToggleSelected}
                      onOpen={onOpenFile}
                      onEditFile={onEditFile}
                      onFileContextMenu={onFileContextMenu}
                      onToggleMenu={handleToggleFileMenu}
                      onRequestMove={onRequestMove}
                      onRequestDelete={onRequestDelete}
                      onDragStart={handleFileDragStart}
                      onDragEnd={resetDrag}
                    />
                  ))}
                </div>
              </section>
            ) : null}
          </>
        ) : (
          emptyState
        )}

        <footer className="library-board__footer">
          <span>
            <Icon name="arrow-down" size={13} />
            {t("library.board.footerUpload")}
          </span>
          <span className="library-board__footer-note">
            {t("library.board.footerBeforeAlt")}
            <kbd>Alt</kbd>
            {t("library.board.footerAfterAlt")}
          </span>
        </footer>
      </div>
    </div>
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
  const { t } = useI18n();
  if (!dragFile && !externalDrag) {
    return null;
  }
  const hint =
    dropTarget !== null ? dropLabelFor(dropTarget) : t("library.board.dragBarHint");
  return (
    <div
      className={["library-dragbar", dropTarget !== null && !dropAllowed ? "is-blocked" : null]
        .filter(Boolean)
        .join(" ")}
      role="status"
      aria-live="polite"
    >
      <Icon name={dragFile ? "leaf" : "arrow-down"} size={15} />
      <span className="library-dragbar__label">
        {dragFile
          ? t("library.board.dragBarFile", { name: dragFile.file_name })
          : t("library.board.incomingFiles")}
      </span>
      <span className="library-dragbar__hint">{hint}</span>
    </div>
  );
}
