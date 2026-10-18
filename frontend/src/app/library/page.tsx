import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import "./library.css";

import type { FileSchema, PathFileSchema } from "../generated-apis-types/schemas";
import { copyFile, moveFile, uploadFile } from "../generated-apis-types/files/files";
import { useSeedDemo } from "../generated-apis-types/system/system";
import { useReadPath } from "../generated-apis-types/tree/tree";
import { parentPath, pathSegments } from "../../lib/format";
import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { QueryState } from "../component/QueryState";
import { useToast } from "../component/Toast";
import { useDebouncedValue } from "../hook/useDebouncedValue";
import { FileReader } from "./component/FileReader";
import { LibraryBoard } from "./component/LibraryBoard";
import { LibraryResults } from "./component/LibraryResults";
import { LibraryToolbar } from "./component/LibraryToolbar";
import { MoveCopyDialog } from "./component/MoveCopyDialog";
import { NewFolderDialog } from "./component/NewFolderDialog";
import { UploadDialog } from "./component/UploadDialog";
import {
  ACCEPTED_FILE_HINT,
  MAX_UPLOAD_BYTES,
  describeError,
  isAcceptedFileName,
  isNotFoundError,
  isSafeUploadName,
  joinArchivePath,
  normalizeLibraryPath,
  parsePositiveInt,
  pathParamValue,
  readerBackLabel,
  sameArchivePath,
  type LibraryUploadTask,
  type LibraryView,
} from "./component/library-utils";
import { useMediaQuery } from "./hook/useMediaQuery";

interface ParamUpdates {
  readonly [key: string]: string | number | null;
}

type FileOperationMode = "move" | "copy";

interface MoveCopyRequest {
  readonly file: PathFileSchema;
  readonly mode: FileOperationMode;
}

function resolveView(rawView: string | null, isDesktop: boolean): LibraryView {
  if (rawView === "board" || rawView === "list") {
    return rawView;
  }
  return isDesktop ? "board" : "list";
}

/**
 * The file shelf. Browse state lives entirely in the query string:
 * `path`, `file`, `chunk` (1-based), `q` (fuzzy path search), and `view`
 * (`board` or `list`). Directory and file clicks push history; search typing,
 * chunk turns, and the view toggle replace it.
 */
export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const isDesktop = useMediaQuery("(min-width: 761px)");
  const nextUploadId = useRef(1);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadTarget, setUploadTarget] = useState("/");
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [moveCopyRequest, setMoveCopyRequest] = useState<MoveCopyRequest | null>(null);
  const [uploadTasks, setUploadTasks] = useState<readonly LibraryUploadTask[]>([]);

  const path = normalizeLibraryPath(searchParams.get("path"));
  const fileId = parsePositiveInt(searchParams.get("file"));
  const requestedChunk = parsePositiveInt(searchParams.get("chunk")) ?? 1;
  const rawQuery = searchParams.get("q") ?? "";
  const query = rawQuery.trim();
  const debouncedQuery = useDebouncedValue(query, 300);
  const activeQuery = query.length > 0 ? debouncedQuery.trim() : "";
  const view = resolveView(searchParams.get("view"), isDesktop);

  const browseQuery = useReadPath(
    {
      path,
      path_depth: 1,
      fuzzy_search: activeQuery || undefined,
    },
    { query: { enabled: fileId === null } },
  );

  // Opening a folder or a reader should start at the masthead, not wherever
  // the previous shelf happened to be scrolled. Query typing does not move it.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [path, fileId]);

  const seedMutation = useSeedDemo({
    mutation: {
      onSuccess: () => {
        toast.success("Demo archive seeded. The shelf is ready.");
        void queryClient.invalidateQueries();
        setSearchParams(new URLSearchParams(), { replace: true });
      },
      onError: (error) => {
        toast.error(describeError(error));
      },
    },
  });

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
      updateParams({
        path: pathParamValue(folderPath || "/"),
        file: null,
        chunk: null,
        q: null,
      });
    },
    [updateParams],
  );

  const selectFile = useCallback(
    (nextFileId: number) => {
      // Keep the current browse path and query so closing the reader returns
      // to the same directory or fuzzy result set.
      updateParams({ file: nextFileId, chunk: 1 });
    },
    [updateParams],
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
      toast.success(`“${file.file_name}” archived as version ${file.version}.`);
      void queryClient.invalidateQueries();
      updateParams({
        path: pathParamValue(parentPath(file.raw_file_path)),
        file: file.id,
        chunk: 1,
        q: null,
      });
    },
    [queryClient, toast, updateParams],
  );

  const closeReader = useCallback(() => {
    updateParams({ file: null, chunk: null });
  }, [updateParams]);

  const clearQuery = useCallback(() => {
    updateParams({ q: null }, { replace: true });
  }, [updateParams]);

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

  const handleChunkChange = (nextChunk: number) => {
    if (fileId === null) {
      return;
    }
    updateParams({ file: fileId, chunk: Math.max(1, nextChunk) }, { replace: true });
  };

  const handleDeleted = useCallback(() => {
    updateParams({ file: null, chunk: null }, { replace: true });
  }, [updateParams]);

  const handleViewChange = useCallback(
    (nextView: LibraryView) => {
      updateParams({ view: nextView }, { replace: true });
    },
    [updateParams],
  );

  const updateUploadTask = useCallback(
    (id: number, updates: Partial<LibraryUploadTask>) => {
      setUploadTasks((current) =>
        current.map((task) => (task.id === id ? { ...task, ...updates } : task)),
      );
    },
    [],
  );

  const handleFilesDropped = useCallback(
    async (files: readonly File[], targetFolder: string) => {
      const accepted: Array<{ readonly id: number; readonly file: File }> = [];
      const rejected: LibraryUploadTask[] = [];

      for (const file of files) {
        const id = nextUploadId.current;
        nextUploadId.current += 1;
        const targetPath = joinArchivePath(targetFolder, file.name);
        if (!isSafeUploadName(file.name) || !isAcceptedFileName(file.name)) {
          rejected.push({
            id,
            name: file.name || "Unnamed file",
            targetPath,
            status: "error",
            message: `Allowed types: ${ACCEPTED_FILE_HINT}.`,
          });
          continue;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
          rejected.push({
            id,
            name: file.name,
            targetPath,
            status: "error",
            message: "Larger than the 10 MB upload limit.",
          });
          continue;
        }
        accepted.push({ id, file });
      }

      const queued: LibraryUploadTask[] = accepted.map(({ id, file }) => ({
        id,
        name: file.name,
        targetPath: joinArchivePath(targetFolder, file.name),
        status: "queued",
      }));

      if (queued.length > 0 || rejected.length > 0) {
        setUploadTasks((current) => [...current, ...queued, ...rejected]);
      }
      if (rejected.length > 0) {
        toast.error(
          `${rejected.length} ${rejected.length === 1 ? "file was" : "files were"} rejected. See the intake queue.`,
        );
      }
      if (accepted.length === 0) {
        return;
      }

      let archived = 0;
      for (const item of accepted) {
        updateUploadTask(item.id, { status: "uploading" });
        try {
          await uploadFile({
            path: joinArchivePath(targetFolder, item.file.name),
            file: item.file,
          });
          archived += 1;
          updateUploadTask(item.id, {
            status: "done",
            message: `Archived in ${targetFolder}`,
          });
        } catch (error) {
          updateUploadTask(item.id, {
            status: "error",
            message: describeError(error),
          });
        }
      }

      await queryClient.invalidateQueries();
      if (archived > 0) {
        toast.success(
          `${archived} ${archived === 1 ? "file" : "files"} archived in ${targetFolder}.`,
        );
      }
    },
    [queryClient, toast, updateUploadTask],
  );

  const handleOperationDone = useCallback(
    (result: FileSchema, targetFolder: string, mode: FileOperationMode) => {
      void queryClient.invalidateQueries();
      if (mode === "move") {
        toast.success(`“${result.file_name}” moved to ${targetFolder}.`);
        if (fileId === result.id) {
          updateParams(
            {
              path: pathParamValue(parentPath(result.raw_file_path)),
              file: result.id,
              chunk: requestedChunk,
              q: null,
            },
            { replace: true },
          );
        }
      } else {
        toast.success(`“${result.file_name}” copied to ${targetFolder} as #${result.id}.`);
      }
      setMoveCopyRequest(null);
    },
    [fileId, queryClient, requestedChunk, toast, updateParams],
  );

  const handleDropMoveCopy = useCallback(
    async (file: PathFileSchema, targetFolder: string, mode: FileOperationMode) => {
      if (mode === "move" && sameArchivePath(parentPath(file.raw_file_path), targetFolder)) {
        toast.info(`“${file.file_name}” already lives in ${targetFolder}.`);
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
    [handleOperationDone, toast],
  );

  const handleRequestMoveCopy = useCallback((file: PathFileSchema, mode: FileOperationMode) => {
    setMoveCopyRequest({ file, mode });
  }, []);

  const listing = browseQuery.data;
  const folderCount = activeQuery ? 0 : (listing?.directories.length ?? 0);
  const fileCount = listing?.files.length ?? 0;
  const settling = query !== activeQuery;

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

  return (
    <div className="page library-page">
      <PageHeader
        eyebrow="Library · file shelf"
        title="Every file has a branch."
        description="Browse current leaves by path, drop files onto a branch, move or copy a leaf without rewriting its history, and read every edition chunk by chunk."
        meta={<span>read_path · 1-based chunks · soft delete keeps history</span>}
        actions={
          <div className="library-actions">
            <Badge tone="moss" dot>
              Current leaves
            </Badge>
            <Badge tone="ochre">Versions branch</Badge>
            <Button variant="primary" size="sm" onClick={() => openUpload()}>
              <Icon name="plus" size={15} />
              Add file
            </Button>
          </div>
        }
      />

      {fileId !== null ? (
        <FileReader
          fileId={fileId}
          requestedChunk={requestedChunk}
          query={query}
          backLabel={readerBackLabel(path, query.length > 0)}
          onClose={closeReader}
          onChunkChange={handleChunkChange}
          onOpenFolder={openFolder}
          onDeleted={handleDeleted}
          onClearQuery={clearQuery}
        />
      ) : (
        <>
          <LibraryToolbar
            path={path}
            rawQuery={rawQuery}
            activeQuery={activeQuery}
            folderCount={folderCount}
            fileCount={fileCount}
            loading={browseQuery.isLoading}
            settling={settling}
            view={view}
            onNavigate={openFolder}
            onQueryChange={handleQueryChange}
            onQuerySubmit={handleQuerySubmit}
            onClearQuery={clearQuery}
            onViewChange={handleViewChange}
          />

          {browseQuery.error && isNotFoundError(browseQuery.error) ? (
            <Panel tone="plain" className="library-not-found reveal reveal-3">
              <p className="eyebrow">Path not found</p>
              <h2>This folder is not on the shelf.</h2>
              <p>
                The archive has no current folder at <code>{path}</code>. It may have been removed
                with its last leaf, or the link may be out of date.
              </p>
              <div className="library-not-found__actions">
                <Button variant="secondary" size="sm" onClick={() => openFolder("/")}>
                  Back to archive root
                </Button>
              </div>
            </Panel>
          ) : (
            <QueryState
              loading={browseQuery.isLoading}
              error={browseQuery.error}
              loadingLabel="Reading the shelf"
            >
              {listing && view === "board" ? (
                <LibraryBoard
                  listing={listing}
                  path={path}
                  query={activeQuery}
                  seeding={seedMutation.isPending}
                  uploads={uploadTasks}
                  onOpenFolder={openFolder}
                  onOpenFile={selectFile}
                  onUpload={() => openUpload()}
                  onUploadHere={(folderPath) => openUpload(folderPath)}
                  onNewFolder={() => setNewFolderOpen(true)}
                  onClearSearch={clearQuery}
                  onSeed={() => seedMutation.mutate()}
                  onDismissUploads={() => setUploadTasks([])}
                  onMoveFile={(file, targetFolder, mode) => {
                    void handleDropMoveCopy(file, targetFolder, mode);
                  }}
                  onRequestMove={handleRequestMoveCopy}
                  onFilesDropped={(files, targetFolder) => {
                    void handleFilesDropped(files, targetFolder);
                  }}
                />
              ) : null}
              {listing && view === "list" ? (
                <LibraryResults
                  listing={listing}
                  query={activeQuery}
                  seeding={seedMutation.isPending}
                  onOpenFolder={openFolder}
                  onOpenFile={selectFile}
                  onUpload={() => openUpload()}
                  onClearSearch={clearQuery}
                  onSeed={() => seedMutation.mutate()}
                />
              ) : null}
            </QueryState>
          )}
        </>
      )}

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
          onCreated={() => setNewFolderOpen(false)}
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
    </div>
  );
}
