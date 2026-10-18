import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import "./library.css";

import type { FileSchema } from "../generated-apis-types/schemas";
import { useSeedDemo } from "../generated-apis-types/system/system";
import { useReadPath } from "../generated-apis-types/tree/tree";
import { parentPath } from "../../lib/format";
import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { QueryState } from "../component/QueryState";
import { useToast } from "../component/Toast";
import { useDebouncedValue } from "../hook/useDebouncedValue";
import { FileReader } from "./component/FileReader";
import { LibraryResults } from "./component/LibraryResults";
import { LibraryToolbar } from "./component/LibraryToolbar";
import { UploadDialog } from "./component/UploadDialog";
import {
  describeError,
  isNotFoundError,
  normalizeLibraryPath,
  parsePositiveInt,
  pathParamValue,
  readerBackLabel,
} from "./component/library-utils";

interface ParamUpdates {
  readonly [key: string]: string | number | null;
}

/**
 * The file shelf. Browse state lives entirely in the query string:
 * `path`, `file`, `chunk` (1-based), and `q` (fuzzy path search). Directory and
 * file clicks push history; search typing and chunk turns replace it.
 */
export function LibraryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [uploadOpen, setUploadOpen] = useState(false);

  const path = normalizeLibraryPath(searchParams.get("path"));
  const fileId = parsePositiveInt(searchParams.get("file"));
  const requestedChunk = parsePositiveInt(searchParams.get("chunk")) ?? 1;
  const rawQuery = searchParams.get("q") ?? "";
  const query = rawQuery.trim();
  const debouncedQuery = useDebouncedValue(query, 300);
  const activeQuery = query.length > 0 ? debouncedQuery.trim() : "";

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

  const listing = browseQuery.data;
  const folderCount = activeQuery ? 0 : (listing?.directories.length ?? 0);
  const fileCount = listing?.files.length ?? 0;
  const settling = query !== activeQuery;

  return (
    <div className="page library-page">
      <PageHeader
        eyebrow="Library · file shelf"
        title="Every file has a branch."
        description="Browse current leaves by path, read them chunk by chunk, and let a new upload branch the same path instead of erasing it. Earlier editions stay in history."
        meta={<span>read_path · 1-based chunks · soft delete keeps history</span>}
        actions={
          <div className="library-actions">
            <Badge tone="moss" dot>
              Current leaves
            </Badge>
            <Badge tone="ochre">Versions branch</Badge>
            <Button variant="primary" size="sm" onClick={() => setUploadOpen(true)}>
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
            onNavigate={openFolder}
            onQueryChange={handleQueryChange}
            onQuerySubmit={handleQuerySubmit}
            onClearQuery={clearQuery}
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
              {listing ? (
                <LibraryResults
                  listing={listing}
                  query={activeQuery}
                  seeding={seedMutation.isPending}
                  onOpenFolder={openFolder}
                  onOpenFile={selectFile}
                  onUpload={() => setUploadOpen(true)}
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
          currentPath={path}
          onClose={() => setUploadOpen(false)}
          onUploaded={openCreatedFile}
        />
      ) : null}
    </div>
  );
}
