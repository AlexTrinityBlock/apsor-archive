import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { IngestJobSchema } from "../../generated-apis-types/schemas";
import {
  retryIngestJob,
  uploadFileAsync,
} from "../../generated-apis-types/files/files";
import { useToast } from "../../component/Toast";
import { useI18n } from "../../i18n";
import { parentPath } from "../../../lib/format";
import {
  ACCEPTED_FILE_HINT,
  MAX_UPLOAD_BYTES,
  describeError,
  ingestJobFailureMessage,
  invalidateLibraryQueries,
  isAbortError,
  isAcceptedFileName,
  isSafeUploadName,
  joinArchivePath,
  taskProgressFromJob,
  waitForIngestJob,
  type LibraryUploadTask,
} from "../component/library-utils";

export interface LibraryUploadsState {
  readonly tasks: readonly LibraryUploadTask[];
  readonly enqueueFiles: (files: readonly File[], targetFolder: string) => Promise<void>;
  readonly retryTask: (task: LibraryUploadTask) => void;
  readonly dismiss: () => void;
}

/**
 * Owns the Library's shared upload queue. Drag/drop, clipboard paste, the
 * Media tab picker, and retries all pass through the same file ingest endpoint
 * and the same tray state.
 */
export function useLibraryUploads(): LibraryUploadsState {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t, formatNumber } = useI18n();
  const nextUploadId = useRef(1);
  const controllers = useRef<Map<number, AbortController>>(new Map());
  const [tasks, setTasks] = useState<readonly LibraryUploadTask[]>([]);

  useEffect(() => {
    const owned = controllers.current;
    return () => {
      for (const controller of owned.values()) {
        controller.abort();
      }
      owned.clear();
    };
  }, []);

  const updateTask = useCallback(
    (id: number, updates: Partial<LibraryUploadTask>) => {
      setTasks((current) =>
        current.map((task) => (task.id === id ? { ...task, ...updates } : task)),
      );
    },
    [],
  );

  const completeTask = useCallback(
    (id: number, job: IngestJobSchema, targetFolder: string) => {
      updateTask(id, {
        ...taskProgressFromJob(job),
        status: "done",
        message: t("library.tray.archivedIn", { folder: targetFolder }),
        rejected: false,
      });
      invalidateLibraryQueries(queryClient, {
        paths: true,
        stats: true,
        timeline: true,
        search: true,
        fileIds: job.file_id !== null ? [job.file_id] : [],
      });
    },
    [queryClient, t, updateTask],
  );

  const followJob = useCallback(
    async (
      id: number,
      jobId: number,
      targetFolder: string,
      controller: AbortController,
    ): Promise<boolean> => {
      const finalJob = await waitForIngestJob(jobId, {
        signal: controller.signal,
        onUpdate: (snapshot) => {
          updateTask(id, {
            ...taskProgressFromJob(snapshot),
            status: snapshot.status === "failed" ? "error" : "processing",
            message:
              snapshot.status === "failed" ? ingestJobFailureMessage(snapshot) : undefined,
          });
        },
      });
      if (controller.signal.aborted) {
        return false;
      }
      completeTask(id, finalJob, targetFolder);
      return true;
    },
    [completeTask, updateTask],
  );

  const runUpload = useCallback(
    async (
      id: number,
      file: File,
      targetFolder: string,
      targetPath: string,
    ): Promise<boolean> => {
      const controller = new AbortController();
      controllers.current.set(id, controller);
      updateTask(id, { status: "uploading", message: undefined, rejected: false });
      try {
        const job = await uploadFileAsync({ path: targetPath, file });
        if (controller.signal.aborted) {
          return false;
        }
        updateTask(id, {
          ...taskProgressFromJob(job),
          status: "processing",
          message: undefined,
        });
        return await followJob(id, job.id, targetFolder, controller);
      } catch (error) {
        if (controller.signal.aborted || isAbortError(error)) {
          return false;
        }
        updateTask(id, { status: "error", message: describeError(error) });
        return false;
      } finally {
        controllers.current.delete(id);
      }
    },
    [followJob, updateTask],
  );

  const runRetry = useCallback(
    async (task: LibraryUploadTask): Promise<boolean> => {
      if (task.status !== "error" || task.rejected) {
        return false;
      }
      const controller = new AbortController();
      controllers.current.set(task.id, controller);
      updateTask(task.id, { status: "processing", message: undefined });
      try {
        let job: IngestJobSchema;
        if (typeof task.jobId === "number") {
          job = await retryIngestJob(task.jobId);
        } else if (task.sourceFile) {
          job = await uploadFileAsync({ path: task.targetPath, file: task.sourceFile });
        } else {
          updateTask(task.id, {
            status: "error",
            message: t("library.tray.cannotRetry"),
          });
          return false;
        }
        if (controller.signal.aborted) {
          return false;
        }
        updateTask(task.id, {
          ...taskProgressFromJob(job),
          status: "processing",
          message: undefined,
        });
        return await followJob(
          task.id,
          job.id,
          parentPath(task.targetPath),
          controller,
        );
      } catch (error) {
        if (controller.signal.aborted || isAbortError(error)) {
          return false;
        }
        updateTask(task.id, { status: "error", message: describeError(error) });
        return false;
      } finally {
        controllers.current.delete(task.id);
      }
    },
    [followJob, t, updateTask],
  );

  const enqueueFiles = useCallback(
    async (files: readonly File[], targetFolder: string) => {
      const accepted: Array<{
        readonly id: number;
        readonly file: File;
        readonly targetPath: string;
      }> = [];
      const rejected: LibraryUploadTask[] = [];

      for (const file of files) {
        const id = nextUploadId.current;
        nextUploadId.current += 1;
        const displayName = file.name.trim() || t("library.tray.unnamedFile");
        const targetPath = joinArchivePath(targetFolder, file.name);
        if (!isSafeUploadName(file.name) || !isAcceptedFileName(file.name)) {
          rejected.push({
            id,
            name: displayName,
            targetPath,
            status: "error",
            rejected: true,
            message: t("library.tray.allowedTypes", { types: ACCEPTED_FILE_HINT }),
          });
          continue;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
          rejected.push({
            id,
            name: displayName,
            targetPath,
            status: "error",
            rejected: true,
            message: t("library.tray.tooLarge"),
          });
          continue;
        }
        accepted.push({ id, file, targetPath });
      }

      const queued: LibraryUploadTask[] = accepted.map(({ id, file, targetPath }) => ({
        id,
        name: file.name,
        targetPath,
        status: "queued",
        stage: "queued",
        sourceFile: file,
      }));

      if (queued.length > 0 || rejected.length > 0) {
        setTasks((current) => [...current, ...queued, ...rejected]);
      }
      if (rejected.length > 0) {
        toast.error(
          t(
            rejected.length === 1
              ? "library.tray.rejectedToastOne"
              : "library.tray.rejectedToastOther",
            { count: formatNumber(rejected.length) },
          ),
        );
      }
      if (accepted.length === 0) {
        return;
      }

      const results = await Promise.all(
        accepted.map(({ id, file, targetPath }) =>
          runUpload(id, file, targetFolder, targetPath),
        ),
      );
      const archived = results.filter(Boolean).length;
      if (archived > 0) {
        toast.success(
          t(
            archived === 1
              ? "library.tray.archivedToastOne"
              : "library.tray.archivedToastOther",
            { count: formatNumber(archived), folder: targetFolder },
          ),
        );
      }
    },
    [formatNumber, runUpload, t, toast],
  );

  const retryTask = useCallback(
    (task: LibraryUploadTask) => {
      void runRetry(task);
    },
    [runRetry],
  );

  const dismiss = useCallback(() => {
    setTasks([]);
  }, []);

  return { tasks, enqueueFiles, retryTask, dismiss };
}
