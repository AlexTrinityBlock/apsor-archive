import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../../apis/fetch-client";
import { getActiveLocale, translate } from "../../i18n";
import type {
  FileSchema,
  IngestJobSchema,
} from "../../generated-apis-types/schemas";
import {
  getFile,
  useReingestFile,
} from "../../generated-apis-types/files/files";
import {
  describeError,
  isAbortError,
  waitForIngestJob,
} from "../component/library-utils";

/** The visible states of one page-level re-ingest run. */
export type ReingestPhase =
  | "idle"
  | "confirming"
  | "enqueueing"
  | "processing"
  | "success"
  | "failure"
  | "already-processing";

export interface FileReingestState {
  readonly phase: ReingestPhase;
  readonly sourceFile: FileSchema | null;
  readonly job: IngestJobSchema | null;
  readonly result: FileSchema | null;
  readonly failureMessage: string | null;
  readonly busy: boolean;
  readonly open: (file: FileSchema) => void;
  readonly confirm: () => void;
  readonly close: () => void;
}

interface UseFileReingestOptions {
  readonly onSuccess: (source: FileSchema, result: FileSchema) => void;
}

/**
 * Owns one Library-level re-ingest run: confirmation, enqueueing, durable-job
 * polling, cancellation, and terminal state. Living at page level means closing
 * the preview does not stop the poll; the job itself continues server-side even
 * when the reader stops waiting.
 */
export function useFileReingest({
  onSuccess,
}: UseFileReingestOptions): FileReingestState {
  const [phase, setPhase] = useState<ReingestPhase>("idle");
  const [sourceFile, setSourceFile] = useState<FileSchema | null>(null);
  const [job, setJob] = useState<IngestJobSchema | null>(null);
  const [result, setResult] = useState<FileSchema | null>(null);
  const [failureMessage, setFailureMessage] = useState<string | null>(null);
  const generation = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const onSuccessRef = useRef(onSuccess);
  const reingestMutation = useReingestFile();
  const enqueue = reingestMutation.mutateAsync;

  useEffect(() => {
    onSuccessRef.current = onSuccess;
  }, [onSuccess]);

  useEffect(
    () => () => {
      generation.current += 1;
      controllerRef.current?.abort();
    },
    [],
  );

  const reset = useCallback(() => {
    generation.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
    setPhase("idle");
    setSourceFile(null);
    setJob(null);
    setResult(null);
    setFailureMessage(null);
  }, []);

  const open = useCallback(
    (file: FileSchema) => {
      if (phase === "enqueueing" || phase === "processing") {
        return;
      }
      generation.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
      setSourceFile(file);
      setJob(null);
      setResult(null);
      setFailureMessage(null);
      setPhase("confirming");
    },
    [phase],
  );

  const confirm = useCallback(() => {
    const source = sourceFile;
    if (source === null || phase !== "confirming") {
      return;
    }
    const runId = generation.current + 1;
    generation.current = runId;
    const controller = new AbortController();
    controllerRef.current = controller;
    setJob(null);
    setResult(null);
    setFailureMessage(null);
    setPhase("enqueueing");

    void (async () => {
      try {
        const queued = await enqueue({
          fileId: source.id,
          data: { expected_version: source.version },
        });
        if (runId !== generation.current) {
          return;
        }
        setJob(queued);
        setPhase("processing");

        const finished = await waitForIngestJob(queued.id, {
          signal: controller.signal,
          onUpdate: (snapshot) => {
            if (runId === generation.current) {
              setJob(snapshot);
            }
          },
        });
        if (runId !== generation.current) {
          return;
        }
        if (finished.file_id === null) {
          throw new Error(
            translate(getActiveLocale(), "library.ingest.missingFile"),
          );
        }
        const next = await getFile(finished.file_id, {
          signal: controller.signal,
        });
        if (runId !== generation.current) {
          return;
        }
        setResult(next);
        setPhase("success");
        onSuccessRef.current(source, next);
      } catch (error) {
        if (runId !== generation.current) {
          return;
        }
        if (controller.signal.aborted || isAbortError(error)) {
          return;
        }
        if (
          error instanceof ApiError &&
          error.code === "ingest_job_conflict"
        ) {
          setFailureMessage(null);
          setPhase("already-processing");
          return;
        }
        setFailureMessage(describeError(error));
        setPhase("failure");
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
        }
      }
    })();
  }, [enqueue, phase, sourceFile]);

  const busy = phase === "enqueueing" || phase === "processing";

  return {
    phase,
    sourceFile,
    job,
    result,
    failureMessage,
    busy,
    open,
    confirm,
    close: reset,
  };
}
