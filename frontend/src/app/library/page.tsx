import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import "./library.css";
import "../viewer/viewer.css";

import type {
  DirectorySchema,
  FileSchema,
  LibraryDeleteResultSchema,
  PathFileSchema,
} from "../generated-apis-types/schemas";
import {
  copyFile,
  moveFile,
} from "../generated-apis-types/files/files";
import { useReadPath } from "../generated-apis-types/tree/tree";
import { basename, parentPath, pathSegments } from "../../lib/format";
import { Button } from "../component/Button";
import {
  ContextMenu,
  type ContextMenuItem,
} from "../component/ContextMenu";
import { Panel } from "../component/Panel";
import { QueryState } from "../component/QueryState";
import { useToast } from "../component/Toast";
import { useI18n } from "../i18n";
import { useDebouncedValue } from "../hook/useDebouncedValue";
import { fileDownloadUrl } from "../viewer/component/viewer-utils";
import { BatchMoveDialog, type BatchMoveResult } from "./component/BatchMoveDialog";
import { DeleteFileDialog } from "./component/DeleteFileDialog";
import { DeleteSelectionDialog } from "./component/DeleteSelectionDialog";
import { FilePreviewModal } from "./component/FilePreviewModal";
import { LibraryFilesContent } from "./component/LibraryFilesContent";
import { LibraryMediaGallery } from "./component/LibraryMediaGallery";
import { LibrarySelectionBar } from "./component/LibrarySelectionBar";
import { LibraryToolbar } from "./component/LibraryToolbar";
import { LibraryUploadTray } from "./component/LibraryUploadTray";
import { MarkdownEditorDialog } from "./component/MarkdownEditorDialog";
import { MoveCopyDialog } from "./component/MoveCopyDialog";
import { NewFolderDialog } from "./component/NewFolderDialog";
import { RenameFileDialog } from "./component/RenameFileDialog";
import { UploadDialog } from "./component/UploadDialog";
import {
  IMAGE_UPLOAD_ACCEPT,
  clipboardFiles,
  describeError,
  filterImageFiles,
  imageFiles,
  invalidateLibraryQueries,
  isEditablePasteTarget,
  isImageFileName,
  isMarkdownFile,
  isNotFoundError,
  joinArchivePath,
  nameClipboardFile,
  normalizeLibraryPath,
  parsePositiveInt,
  pathParamValue,
  sameArchivePath,
  sortListing,
  type FileOperationMode,
  type FileOperationTarget,
  type LibraryContextMenuTrigger,
  type LibrarySort,
  type LibraryTab,
  type LibraryView,
} from "./component/library-utils";
import { useLibraryUploads } from "./hook/useLibraryUploads";
import { useMediaQuery } from "./hook/useMediaQuery";

interface ParamUpdates {
  readonly [key: string]: string | number | null;
}

interface MoveCopyRequest {
  readonly file: FileOperationTarget;
  readonly mode: FileOperationMode;
}

interface DeleteRequest {
  readonly file_id: number;
  readonly file_name: string;
  readonly raw_file_path: string;
}

interface DeleteSelectionRequest {
  readonly files: readonly PathFileSchema[];
  readonly folders: readonly DirectorySchema[];
  readonly afterDeletePath?: string | null;
}

type LibraryContextTarget =
  | { readonly kind: "file"; readonly file: PathFileSchema }
  | { readonly kind: "folder"; readonly folder: DirectorySchema };

interface LibraryContextMenuState {
  readonly x: number;
  readonly y: number;
  readonly target: LibraryContextTarget;
  readonly returnFocus: HTMLElement | null;
}

const EMPTY_SELECTED_FILE_IDS: ReadonlySet<number> = new Set<number>();
const EMPTY_SELECTED_FOLDER_PATHS: ReadonlySet<string> = new Set<string>();

function resolveView(rawView: string | null, isDesktop: boolean): LibraryView {
  if (rawView === "board" || rawView === "list") {
    return rawView;
  }
  return isDesktop ? "board" : "list";
}

interface RenameRequestDialogProps {
  readonly request: FileOperationTarget | null;
  readonly onClose: () => void;
}

/** Renders the optional rename dialog without adding another branch to the page. */
function RenameRequestDialog({
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

interface DeleteSelectionDialogRequestProps {
  readonly request: DeleteSelectionRequest | null;
  readonly onClose: () => void;
  readonly onDeleted: (result: LibraryDeleteResultSchema) => void;
}

/** Renders the batch-delete dialog without adding another branch to the page. */
function DeleteSelectionDialogRequest({
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
function LibrarySelectionBarSlot({
  tab,
  selecting,
  ...barProps
}: LibrarySelectionBarSlotProps) {
  if (tab !== "files" || !selecting) {
    return null;
  }
  return <LibrarySelectionBar {...barProps} />;
}

/**
 * The unified file workspace. One `readPath` listing feeds both the Files tab
 * and the image-only Media gallery; the preview modal keeps the shelf behind
 * it. Browse state lives in the query string: `tab`, `path`, `q`, `view`,
 * `file`, `chunk`, and `media` (an image file id).
 */
export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t, formatNumber } = useI18n();
  const isDesktop = useMediaQuery("(min-width: 761px)");
  const mediaInputRef = useRef<HTMLInputElement>(null);
  const {
    tasks: uploadTasks,
    enqueueFiles,
    retryTask: handleRetryTask,
    dismiss: dismissUploads,
  } = useLibraryUploads();

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadTarget, setUploadTarget] = useState("/");
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newMarkdownDirectory, setNewMarkdownDirectory] = useState("/");
  const [newMarkdownOpen, setNewMarkdownOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<LibraryContextMenuState | null>(
    null,
  );
  const [moveCopyRequest, setMoveCopyRequest] = useState<MoveCopyRequest | null>(null);
  const [deleteRequest, setDeleteRequest] = useState<DeleteRequest | null>(null);
  const [renameRequest, setRenameRequest] = useState<FileOperationTarget | null>(
    null,
  );
  const [selecting, setSelecting] = useState(false);
  const [selectedFileIds, setSelectedFileIds] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const [selectedFolderPaths, setSelectedFolderPaths] = useState<
    ReadonlySet<string>
  >(() => new Set<string>());
  const [selectionPath, setSelectionPath] = useState<string | null>(null);
  const [batchMoveFiles, setBatchMoveFiles] = useState<readonly PathFileSchema[] | null>(null);
  const [deleteSelectionRequest, setDeleteSelectionRequest] =
    useState<DeleteSelectionRequest | null>(null);
  const [sort, setSort] = useState<LibrarySort>("modified");
  const [mediaFilter, setMediaFilter] = useState("");

  const rawTab = searchParams.get("tab");
  const tab: LibraryTab = rawTab === "media" ? "media" : "files";
  const path = normalizeLibraryPath(searchParams.get("path"));
  const fileId = parsePositiveInt(searchParams.get("file"));
  const mediaId = parsePositiveInt(searchParams.get("media"));
  const previewFileId = tab === "media" ? mediaId ?? fileId : fileId;
  const requestedChunk = parsePositiveInt(searchParams.get("chunk")) ?? 1;
  const rawQuery = tab === "files" ? searchParams.get("q") ?? "" : "";
  const query = rawQuery.trim();
  const debouncedQuery = useDebouncedValue(query, 300);
  const activeQuery = query.length > 0 ? debouncedQuery.trim() : "";
  const view = resolveView(searchParams.get("view"), isDesktop);
  const startInEdit = searchParams.get("mode") === "edit";

  const browseQuery = useReadPath({
    path,
    path_depth: 1,
    fuzzy_search: tab === "files" && activeQuery ? activeQuery : undefined,
  });

  const resetSelection = useCallback(() => {
    setSelecting(false);
    setSelectedFileIds(new Set<number>());
    setSelectedFolderPaths(new Set<string>());
    setSelectionPath(null);
  }, []);

  const updateParams = useCallback(
    (updates: ParamUpdates, options?: { readonly replace?: boolean }) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(updates)) {
            if (value === null || value === "") {
              next.delete(key);
            } else {
              next.set(key, String(value));
            }
          }
          return next;
        },
        { replace: options?.replace ?? false },
      );
    },
    [setSearchParams],
  );

  const openFolder = useCallback(
    (folderPath: string) => {
      resetSelection();
      setMediaFilter("");
      updateParams({
        path: pathParamValue(folderPath || "/"),
        file: null,
        media: null,
        chunk: null,
        q: null,
        mode: null,
      });
    },
    [resetSelection, updateParams],
  );

  const openPreview = useCallback(
    (nextFileId: number) => {
      resetSelection();
      if (tab === "media") {
        updateParams({ media: nextFileId, file: null, chunk: null, mode: null });
      } else {
        updateParams({ file: nextFileId, media: null, chunk: null, mode: null });
      }
    },
    [resetSelection, tab, updateParams],
  );

  const closePreview = useCallback(() => {
    updateParams(
      { file: null, media: null, chunk: null, mode: null },
      { replace: true },
    );
  }, [updateParams]);

  const handleEditModeChange = useCallback(
    (editing: boolean) => {
      updateParams({ mode: editing ? "edit" : null }, { replace: true });
    },
    [updateParams],
  );

  const openMarkdownEditor = useCallback(
    (nextFileId: number) => {
      resetSelection();
      setMediaFilter("");
      updateParams({
        tab: null,
        file: nextFileId,
        mode: "edit",
        media: null,
        chunk: null,
        q: null,
      });
    },
    [resetSelection, updateParams],
  );

  const openNewMarkdown = useCallback((directory: string) => {
    setNewMarkdownDirectory(normalizeLibraryPath(directory));
    setNewMarkdownOpen(true);
  }, []);

  const handleChunkChange = useCallback(
    (nextChunk: number) => {
      if (previewFileId === null) {
        return;
      }
      const chunk = Math.max(1, nextChunk);
      if (tab === "media") {
        updateParams({ media: previewFileId, chunk }, { replace: true });
      } else {
        updateParams({ file: previewFileId, chunk }, { replace: true });
      }
    },
    [previewFileId, tab, updateParams],
  );

  const openUpload = useCallback(
    (targetPath?: string) => {
      setUploadTarget(targetPath ?? path);
      setUploadOpen(true);
    },
    [path],
  );

  const openCreatedFile = useCallback(
    (file: FileSchema) => {
      setUploadOpen(false);
      resetSelection();
      setMediaFilter("");
      toast.success(
        t("library.page.archivedToast", {
          name: file.file_name,
          version: file.version,
        }),
      );
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        search: true,
        fileIds: [file.id],
      });
      const image = isImageFileName(file.file_name) || file.mime_type.startsWith("image/");
      const nextPath = pathParamValue(parentPath(file.raw_file_path));
      if (tab === "media" && image) {
        updateParams({
          tab: "media",
          path: nextPath,
          media: file.id,
          file: null,
          chunk: null,
          q: null,
          mode: null,
        });
      } else {
        updateParams({
          tab: null,
          path: nextPath,
          file: file.id,
          media: null,
          chunk: null,
          q: null,
          mode: null,
        });
      }
    },
    [queryClient, resetSelection, t, tab, toast, updateParams],
  );

  const handleQueryChange = useCallback(
    (value: string) => {
      updateParams({ q: value.length > 0 ? value : null }, { replace: true });
    },
    [updateParams],
  );

  const handleQuerySubmit = useCallback(
    (value: string) => {
      updateParams({ q: value.length > 0 ? value : null }, { replace: true });
    },
    [updateParams],
  );

  const clearQuery = useCallback(() => {
    updateParams({ q: null }, { replace: true });
  }, [updateParams]);

  const handleTabChange = useCallback(
    (nextTab: LibraryTab) => {
      if (nextTab === tab) {
        return;
      }
      resetSelection();
      setMediaFilter("");
      updateParams({
        tab: nextTab === "media" ? "media" : null,
        file: null,
        media: null,
        chunk: null,
        q: null,
        mode: null,
      });
    },
    [resetSelection, tab, updateParams],
  );

  const handleViewChange = useCallback(
    (nextView: LibraryView) => {
      updateParams({ view: nextView }, { replace: true });
    },
    [updateParams],
  );


  // Clipboard files use the same ingest queue as drag/drop. Text paste in
  // inputs, textareas, and contenteditable regions is left to the browser.
  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      if (isEditablePasteTarget(event.target)) {
        return;
      }
      const files = clipboardFiles(event.clipboardData);
      if (files.length === 0) {
        return;
      }
      event.preventDefault();
      const named = files.map((file, index) => nameClipboardFile(file, index));
      void enqueueFiles(named, path);
    };
    window.addEventListener("paste", handlePaste);
    return () => window.removeEventListener("paste", handlePaste);
  }, [enqueueFiles, path]);

  const handleMediaInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    const images = files.filter((file) => isImageFileName(file.name));
    if (images.length === 0) {
      if (files.length > 0) {
        toast.error(t("library.page.imagePickerError"));
      }
      return;
    }
    void enqueueFiles(images, path);
  };

  const openMediaPicker = () => {
    mediaInputRef.current?.click();
  };

  const handleOperationDone = useCallback(
    (result: FileSchema, targetFolder: string, mode: FileOperationMode) => {
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        fileIds: [result.id],
      });
      if (mode === "move") {
        toast.success(
          t("library.page.movedToast", {
            name: result.file_name,
            folder: targetFolder,
          }),
        );
        if (previewFileId === result.id) {
          const nextPath = pathParamValue(parentPath(result.raw_file_path));
          const chunk = requestedChunk > 1 ? requestedChunk : null;
          if (tab === "media") {
            updateParams(
              {
                path: nextPath,
                media: result.id,
                file: null,
                chunk,
                mode: null,
              },
              { replace: true },
            );
          } else {
            updateParams(
              {
                path: nextPath,
                file: result.id,
                media: null,
                chunk,
                mode: null,
              },
              { replace: true },
            );
          }
        }
      } else {
        toast.success(
          t("library.page.copiedToast", {
            name: result.file_name,
            folder: targetFolder,
            id: result.id,
          }),
        );
      }
      setMoveCopyRequest(null);
    },
    [previewFileId, queryClient, requestedChunk, t, tab, toast, updateParams],
  );

  const handleDropMoveCopy = useCallback(
    async (file: FileOperationTarget, targetFolder: string, mode: FileOperationMode) => {
      if (mode === "move" && sameArchivePath(parentPath(file.raw_file_path), targetFolder)) {
        toast.info(
          t("library.page.alreadyThereToast", {
            name: file.file_name,
            folder: targetFolder,
          }),
        );
        return;
      }
      const targetPath = joinArchivePath(targetFolder, file.file_name);
      try {
        const result =
          mode === "move"
            ? await moveFile(file.file_id, { path: targetPath })
            : await copyFile(file.file_id, { path: targetPath });
        handleOperationDone(result, targetFolder, mode);
      } catch (error) {
        toast.error(describeError(error));
      }
    },
    [handleOperationDone, t, toast],
  );

  const handleRequestMoveCopy = useCallback(
    (file: FileOperationTarget, mode: FileOperationMode) => {
      setMoveCopyRequest({ file, mode });
    },
    [],
  );

  const handleRequestDelete = useCallback((target: FileOperationTarget) => {
    setDeleteRequest({
      file_id: target.file_id,
      file_name: target.file_name,
      raw_file_path: target.raw_file_path,
    });
  }, []);

  const handleRequestRename = useCallback((file: FileOperationTarget) => {
    setRenameRequest(file);
  }, []);

  const handleDeleted = useCallback(
    (deletedFileId: number) => {
      setDeleteRequest(null);
      setSelectedFileIds((current) => {
        if (!current.has(deletedFileId)) {
          return current;
        }
        const next = new Set(current);
        next.delete(deletedFileId);
        return next;
      });
      if (previewFileId === deletedFileId) {
        updateParams(
          { file: null, media: null, chunk: null, mode: null },
          { replace: true },
        );
      }
    },
    [previewFileId, updateParams],
  );

  const listing = browseQuery.data;
  const sortedListing = useMemo(
    () => (listing ? sortListing(listing, sort) : undefined),
    [listing, sort],
  );
  const visibleFiles = useMemo(() => sortedListing?.files ?? [], [sortedListing]);
  const visibleFolders = useMemo(
    () => (activeQuery ? [] : sortedListing?.directories ?? []),
    [activeQuery, sortedListing],
  );
  const imageListing = useMemo(() => imageFiles(visibleFiles), [visibleFiles]);
  const visibleImages = useMemo(
    () => filterImageFiles(imageListing, mediaFilter),
    [imageListing, mediaFilter],
  );
  const settling = tab === "files" && query !== activeQuery;

  const activeSelectedFileIds =
    selectionPath === path ? selectedFileIds : EMPTY_SELECTED_FILE_IDS;
  const activeSelectedFolderPaths =
    selectionPath === path ? selectedFolderPaths : EMPTY_SELECTED_FOLDER_PATHS;
  const selectedFiles = useMemo(
    () => visibleFiles.filter((file) => activeSelectedFileIds.has(file.file_id)),
    [activeSelectedFileIds, visibleFiles],
  );
  const selectedFolders = useMemo(
    () => visibleFolders.filter((folder) => activeSelectedFolderPaths.has(folder.path)),
    [activeSelectedFolderPaths, visibleFolders],
  );

  const toggleSelecting = useCallback(() => {
    setSelecting((current) => !current);
    setSelectedFileIds(new Set<number>());
    setSelectedFolderPaths(new Set<string>());
    setSelectionPath(path);
  }, [path]);

  const toggleSelected = useCallback(
    (selectedFileId: number) => {
      setSelectedFileIds((current) => {
        const next = new Set(selectionPath === path ? current : []);
        if (next.has(selectedFileId)) {
          next.delete(selectedFileId);
        } else {
          next.add(selectedFileId);
        }
        return next;
      });
      setSelectionPath(path);
    },
    [path, selectionPath],
  );

  const toggleSelectedFolder = useCallback(
    (folderPath: string) => {
      setSelectedFolderPaths((current) => {
        const next = new Set(selectionPath === path ? current : []);
        if (next.has(folderPath)) {
          next.delete(folderPath);
        } else {
          next.add(folderPath);
        }
        return next;
      });
      setSelectionPath(path);
    },
    [path, selectionPath],
  );

  const selectAllVisible = useCallback(() => {
    setSelectedFileIds(new Set(visibleFiles.map((file) => file.file_id)));
    setSelectedFolderPaths(new Set(visibleFolders.map((folder) => folder.path)));
    setSelectionPath(path);
  }, [path, visibleFiles, visibleFolders]);

  const clearSelection = useCallback(() => {
    setSelectedFileIds(new Set<number>());
    setSelectedFolderPaths(new Set<string>());
  }, []);

  const exitSelection = useCallback(() => {
    setSelecting(false);
    setSelectedFileIds(new Set<number>());
    setSelectedFolderPaths(new Set<string>());
  }, []);

  const requestBatchMove = useCallback(() => {
    if (selectedFiles.length === 0) {
      return;
    }
    setBatchMoveFiles(selectedFiles);
  }, [selectedFiles]);

  const requestDeleteSelected = useCallback(() => {
    const selectedCount = selectedFiles.length + selectedFolders.length;
    if (selectedCount === 0) {
      return;
    }
    setDeleteSelectionRequest({ files: selectedFiles, folders: selectedFolders });
  }, [selectedFiles, selectedFolders]);

  const requestDeleteCurrentFolder = useCallback(() => {
    if (path === "/") {
      return;
    }
    const segments = pathSegments(path);
    setDeleteSelectionRequest({
      files: [],
      folders: [
        {
          depth: segments.length,
          name: basename(path),
          path,
        },
      ],
      afterDeletePath: parentPath(path),
    });
  }, [path]);

  const handleSelectionDeleted = useCallback(
    (result: LibraryDeleteResultSchema) => {
      const afterDeletePath = deleteSelectionRequest?.afterDeletePath ?? null;
      setDeleteSelectionRequest(null);
      exitSelection();
      if (afterDeletePath !== null) {
        updateParams(
          {
            path: pathParamValue(afterDeletePath),
            file: null,
            media: null,
            chunk: null,
            q: null,
            mode: null,
          },
          { replace: true },
        );
        return;
      }
      if (result.deleted_file_ids.includes(previewFileId ?? -1)) {
        updateParams(
          { file: null, media: null, chunk: null, mode: null },
          { replace: true },
        );
      }
    },
    [deleteSelectionRequest, exitSelection, previewFileId, updateParams],
  );

  const handleBatchMoveFinished = useCallback(
    (result: BatchMoveResult) => {
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        fileIds: result.movedIds,
      });
      const moved = new Set(result.movedIds);
      setSelectedFileIds((current) => {
        const next = new Set([...current].filter((id) => !moved.has(id)));
        return next.size === current.size ? current : next;
      });
      if (previewFileId !== null && result.movedIds.includes(previewFileId)) {
        const nextPath = pathParamValue(result.targetFolder);
        const chunk = requestedChunk > 1 ? requestedChunk : null;
        if (tab === "media") {
          updateParams(
            {
              path: nextPath,
              media: previewFileId,
              file: null,
              chunk,
              mode: null,
            },
            { replace: true },
          );
        } else {
          updateParams(
            {
              path: nextPath,
              file: previewFileId,
              media: null,
              chunk,
              mode: null,
            },
            { replace: true },
          );
        }
      }
      if (result.movedIds.length > 0) {
        toast.success(
          t(
            result.movedIds.length === 1
              ? "library.batch.movedToastOne"
              : "library.batch.movedToastOther",
            {
              count: formatNumber(result.movedIds.length),
              folder: result.targetFolder,
            },
          ),
        );
      }
      if (result.skipped > 0) {
        toast.info(
          t(
            result.skipped === 1
              ? "library.batch.skippedToastOne"
              : "library.batch.skippedToastOther",
            { count: formatNumber(result.skipped), folder: result.targetFolder },
          ),
        );
      }
      if (result.failures.length > 0) {
        toast.error(
          t(
            result.failures.length === 1
              ? "library.batch.failuresToastOne"
              : "library.batch.failuresToastOther",
            { count: formatNumber(result.failures.length) },
          ),
        );
      } else {
        setBatchMoveFiles(null);
      }
    },
    [formatNumber, previewFileId, queryClient, requestedChunk, t, tab, toast, updateParams],
  );

  const handleNewMarkdownSaved = useCallback(
    (savedFile: FileSchema) => {
      resetSelection();
      setMediaFilter("");
      const nextPath = pathParamValue(parentPath(savedFile.raw_file_path));
      // Keep the editor dialog open for continuous editing. Only the folder
      // behind it follows the saved file so closing the dialog lands in place.
      updateParams({
        tab: null,
        path: nextPath,
        media: null,
        chunk: null,
        q: null,
      });
    },
    [resetSelection, updateParams],
  );

  const downloadArchiveFile = useCallback((file: PathFileSchema) => {
    // A temporary anchor is safer than window.location: it never leaves the SPA
    // and reuses the download endpoint.
    const anchor = document.createElement("a");
    anchor.href = fileDownloadUrl(file.file_id);
    anchor.download = file.file_name;
    anchor.rel = "noopener";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  }, []);

  const copyArchivePath = useCallback(
    async (archivePath: string) => {
      try {
        await navigator.clipboard.writeText(archivePath);
        toast.success(t("library.contextMenu.pathCopied"));
      } catch {
        toast.error(t("library.errors.generic"));
      }
    },
    [t, toast],
  );

  const openFileContextMenu = useCallback(
    (event: LibraryContextMenuTrigger, file: PathFileSchema) => {
      event.preventDefault();
      event.stopPropagation();
      const returnFocus =
        event.currentTarget instanceof HTMLElement
          ? event.currentTarget
          : null;
      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        target: { kind: "file", file },
        returnFocus,
      });
    },
    [],
  );

  const openFolderContextMenu = useCallback(
    (event: LibraryContextMenuTrigger, folder: DirectorySchema) => {
      event.preventDefault();
      event.stopPropagation();
      const returnFocus =
        event.currentTarget instanceof HTMLElement
          ? event.currentTarget
          : null;
      setContextMenu({
        x: event.clientX,
        y: event.clientY,
        target: { kind: "folder", folder },
        returnFocus,
      });
    },
    [],
  );

  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const contextMenuItems = useMemo<readonly ContextMenuItem[]>(() => {
    if (!contextMenu) {
      return [];
    }

    if (contextMenu.target.kind === "file") {
      const file = contextMenu.target.file;
      const items: ContextMenuItem[] = [
        {
          id: "open",
          label: t("library.contextMenu.open"),
          icon: "file",
          onSelect: () => openPreview(file.file_id),
        },
      ];

      if (isMarkdownFile(file.raw_file_path)) {
        items.push({
          id: "edit",
          label: t("library.contextMenu.editMarkdown"),
          icon: "pencil",
          onSelect: () => openMarkdownEditor(file.file_id),
        });
      }

      items.push({
        id: "rename",
        label: t("library.common.rename"),
        icon: "pencil",
        onSelect: () => handleRequestRename(file),
      });

      if (file.has_original) {
        items.push({
          id: "download",
          label: t("library.contextMenu.download"),
          icon: "arrow-down",
          onSelect: () => downloadArchiveFile(file),
        });
      }

      items.push(
        {
          id: "move",
          label: t("library.contextMenu.move"),
          icon: "branch",
          onSelect: () => handleRequestMoveCopy(file, "move"),
        },
        {
          id: "copy",
          label: t("library.contextMenu.copy"),
          icon: "copy",
          onSelect: () => handleRequestMoveCopy(file, "copy"),
        },
        {
          id: "delete",
          label: t("library.contextMenu.delete"),
          icon: "trash",
          danger: true,
          onSelect: () => handleRequestDelete(file),
        },
        {
          id: "copyPath",
          label: t("library.contextMenu.copyPath"),
          icon: "copy",
          onSelect: () => void copyArchivePath(file.raw_file_path),
        },
      );
      return items;
    }

    const folder = contextMenu.target.folder;
    return [
      {
        id: "open",
        label: t("library.contextMenu.openFolder"),
        icon: "folder",
        onSelect: () => openFolder(folder.path),
      },
      {
        id: "uploadHere",
        label: t("library.contextMenu.uploadHere"),
        icon: "plus",
        onSelect: () => openUpload(folder.path),
      },
      {
        id: "newMarkdownHere",
        label: t("library.contextMenu.newMarkdownHere"),
        icon: "file",
        onSelect: () => openNewMarkdown(folder.path),
      },
      {
        id: "copyPath",
        label: t("library.contextMenu.copyPath"),
        icon: "copy",
        onSelect: () => void copyArchivePath(folder.path),
      },
    ];
  }, [
    contextMenu,
    copyArchivePath,
    downloadArchiveFile,
    handleRequestDelete,
    handleRequestMoveCopy,
    handleRequestRename,
    openFolder,
    openMarkdownEditor,
    openNewMarkdown,
    openPreview,
    openUpload,
    t,
  ]);

  const folderSuggestions = useMemo(() => {
    const suggestions: string[] = [];
    const seen = new Set<string>();
    const add = (candidate: string) => {
      if (!seen.has(candidate)) {
        seen.add(candidate);
        suggestions.push(candidate);
      }
    };
    add(path);
    if (path !== "/") {
      add(parentPath(path));
    }
    const segments = pathSegments(path);
    for (let index = 1; index <= segments.length; index += 1) {
      add(`/${segments.slice(0, index).join("/")}`);
    }
    for (const folder of listing?.directories ?? []) {
      add(folder.path);
    }
    add("/");
    return suggestions;
  }, [listing?.directories, path]);

  let panelContent: ReactNode = null;
  if (tab === "files" && sortedListing) {
    panelContent = (
      <LibraryFilesContent
        listing={{ ...sortedListing, directories: visibleFolders }}
        path={path}
        query={activeQuery}
        view={view}
        selecting={selecting}
        selectedFileIds={activeSelectedFileIds}
        selectedFolderPaths={activeSelectedFolderPaths}
        onToggleSelected={toggleSelected}
        onToggleSelectedFolder={toggleSelectedFolder}
        onOpenFolder={openFolder}
        onOpenFile={openPreview}
        onEditFile={openMarkdownEditor}
        onFileContextMenu={openFileContextMenu}
        onFolderContextMenu={openFolderContextMenu}
        onUpload={() => openUpload()}
        onUploadHere={(folderPath) => openUpload(folderPath)}
        onNewFolder={() => setNewFolderOpen(true)}
        onClearSearch={clearQuery}
        onOpenRoot={() => openFolder("/")}
        onRequestMove={handleRequestMoveCopy}
        onRequestDelete={handleRequestDelete}
        onMoveFile={(file, targetFolder, mode) => {
          void handleDropMoveCopy(file, targetFolder, mode);
        }}
        onFilesDropped={(files, targetFolder) => {
          void enqueueFiles(files, targetFolder);
        }}
      />
    );
  } else if (tab === "media") {
    panelContent = (
      <LibraryMediaGallery
        path={path}
        images={visibleImages}
        totalImages={imageListing.length}
        filter={mediaFilter}
        onFilterChange={setMediaFilter}
        onClearFilter={() => setMediaFilter("")}
        onOpen={openPreview}
        onUploadImage={openMediaPicker}
        onOpenRoot={() => openFolder("/")}
      />
    );
  }

  return (
    <div className="library-page">
      <h1 className="visually-hidden">{t("library.page.title")}</h1>

      <LibraryToolbar
        path={path}
        tab={tab}
        rawQuery={rawQuery}
        activeQuery={activeQuery}
        sort={sort}
        view={view}
        selecting={selecting}
        folderCount={visibleFolders.length}
        fileCount={visibleFiles.length}
        mediaCount={imageListing.length}
        loading={browseQuery.isLoading}
        settling={settling}
        onNavigate={openFolder}
        onQueryChange={handleQueryChange}
        onQuerySubmit={handleQuerySubmit}
        onClearQuery={clearQuery}
        onSortChange={setSort}
        onTabChange={handleTabChange}
        onViewChange={handleViewChange}
        onToggleSelecting={toggleSelecting}
        onUpload={() => openUpload()}
        onNewFolder={() => setNewFolderOpen(true)}
        onDeleteFolder={requestDeleteCurrentFolder}
        onNewMarkdown={() => openNewMarkdown(path)}
      />

      <div
        className="library-canvas"
        id="library-panel"
        role="tabpanel"
        aria-labelledby={tab === "files" ? "library-tab-files" : "library-tab-media"}
      >
        <LibraryUploadTray
          tasks={uploadTasks}
          onRetry={handleRetryTask}
          onDismiss={dismissUploads}
        />

        <LibrarySelectionBarSlot
          tab={tab}
          selecting={selecting}
          selectedFileCount={selectedFiles.length}
          selectedFolderCount={selectedFolders.length}
          visibleCount={visibleFiles.length + visibleFolders.length}
          onSelectAll={selectAllVisible}
          onClear={clearSelection}
          onMoveSelected={requestBatchMove}
          onDeleteSelected={requestDeleteSelected}
          onExit={exitSelection}
        />

        {browseQuery.error && isNotFoundError(browseQuery.error) ? (
          <Panel tone="plain" className="library-not-found">
            <p className="eyebrow">{t("library.page.pathNotFoundEyebrow")}</p>
            <h2>{t("library.page.pathNotFoundTitle")}</h2>
            <p>
              {t("library.page.pathNotFoundBefore")}
              <code>{path}</code>
              {t("library.page.pathNotFoundAfter")}
            </p>
            <div className="library-not-found__actions">
              <Button variant="secondary" size="sm" onClick={() => openFolder("/")}>
                {t("library.common.backToRoot")}
              </Button>
            </div>
          </Panel>
        ) : (
          <QueryState
            loading={browseQuery.isLoading}
            error={browseQuery.error}
            loadingLabel={t("library.page.loadingShelf")}
          >
            {panelContent}
          </QueryState>
        )}
      </div>

      <input
        ref={mediaInputRef}
        type="file"
        accept={IMAGE_UPLOAD_ACCEPT}
        multiple
        className="visually-hidden"
        tabIndex={-1}
        aria-hidden="true"
        onChange={handleMediaInputChange}
      />

      {uploadOpen ? (
        <UploadDialog
          currentPath={uploadTarget}
          onClose={() => setUploadOpen(false)}
          onUploaded={openCreatedFile}
        />
      ) : null}

      {newFolderOpen ? (
        <NewFolderDialog
          currentPath={path}
          onClose={() => setNewFolderOpen(false)}
          onCreated={(createdPath) => {
            setNewFolderOpen(false);
            openFolder(createdPath);
          }}
        />
      ) : null}

      {newMarkdownOpen ? (
        <MarkdownEditorDialog
          defaultDirectory={newMarkdownDirectory}
          onClose={() => setNewMarkdownOpen(false)}
          onSaved={handleNewMarkdownSaved}
        />
      ) : null}

      {moveCopyRequest ? (
        <MoveCopyDialog
          file={moveCopyRequest.file}
          mode={moveCopyRequest.mode}
          currentPath={path}
          suggestions={folderSuggestions}
          onClose={() => setMoveCopyRequest(null)}
          onDone={handleOperationDone}
        />
      ) : null}

      <RenameRequestDialog
        request={renameRequest}
        onClose={() => setRenameRequest(null)}
      />

      {batchMoveFiles ? (
        <BatchMoveDialog
          files={batchMoveFiles}
          currentPath={path}
          suggestions={folderSuggestions}
          onClose={() => setBatchMoveFiles(null)}
          onFinished={handleBatchMoveFinished}
        />
      ) : null}

      <DeleteSelectionDialogRequest
        request={deleteSelectionRequest}
        onClose={() => setDeleteSelectionRequest(null)}
        onDeleted={handleSelectionDeleted}
      />

      {deleteRequest ? (
        <DeleteFileDialog
          fileId={deleteRequest.file_id}
          fileName={deleteRequest.file_name}
          rawFilePath={deleteRequest.raw_file_path}
          onClose={() => setDeleteRequest(null)}
          onDeleted={() => handleDeleted(deleteRequest.file_id)}
        />
      ) : null}

      {previewFileId !== null ? (
        <FilePreviewModal
          fileId={previewFileId}
          requestedChunk={requestedChunk}
          startInEdit={startInEdit}
          onClose={closePreview}
          onChunkChange={handleChunkChange}
          onFileVersionChange={(nextFileId) => {
            updateParams(
              { file: nextFileId, mode: "edit", chunk: null },
              { replace: true },
            );
          }}
          onEditModeChange={handleEditModeChange}
          onMove={(target) => handleRequestMoveCopy(target, "move")}
          onCopy={(target) => handleRequestMoveCopy(target, "copy")}
          onRename={handleRequestRename}
          onDelete={handleRequestDelete}
        />
      ) : null}

      {contextMenu ? (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenuItems}
          label={t("library.contextMenu.label")}
          onClose={closeContextMenu}
          returnFocus={contextMenu.returnFocus}
        />
      ) : null}
    </div>
  );
}
