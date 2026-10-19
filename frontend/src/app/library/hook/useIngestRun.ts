import { useEffect, useRef, useState } from "react";

import type { FileSchema, IngestJobSchema } from "../../generated-apis-types/schemas";
import {
  IngestJobFailureError,
  describeError,
  isAbortError,
  waitForIngestedFile,
} from "../component/library-utils";

export type IngestRunPhase = "idle" | "enqueueing" | "processing";

export interface IngestRunFailure {
  readonly message: string;
  readonly retryJobId: number | null;
}

export interface IngestRunState {
  readonly phase: IngestRunPhase;
  readonly job: IngestJobSchema | null;
  readonly failure: IngestRunFailure | null;
  readonly start: (enqueue: () => Promise<IngestJobSchema>) => void;
  readonly cancel: () => void;
  readonly reset: () => void;
}

/**
 * Owns one dialog-scoped ingestion run: enqueueing, polling, cancellation, and
 * failure state. Polling stops when the caller unmounts or calls `cancel`, but
 * the durable backend job is never cancelled.
 */
export function useIngestRun(onReady: (file: FileSchema) => void): IngestRunState {
  const [phase, setPhase] = useState<IngestRunPhase>("idle");
  const [job, setJob] = useState<IngestJobSchema | null>(null);
  const [failure, setFailure] = useState<IngestRunFailure | null>(null);
  const runGeneration = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const onReadyRef = useRef(onReady);

  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  useEffect(
    () => () => {
      runGeneration.current += 1;
      controllerRef.current?.abort();
    },
    [],
  );

  const followJob = async (generation: number, jobId: number) => {
    const controller = new AbortController();
    controllerRef.current = controller;
    let file: FileSchema | null = null;

    try {
      file = await waitForIngestedFile(jobId, {
        signal: controller.signal,
        onUpdate: (snapshot) => {
          if (generation === runGeneration.current) {
            setJob(snapshot);
          }
        },
      });
    } catch (error) {
      if (generation !== runGeneration.current) {
        return;
      }
      if (controller.signal.aborted || isAbortError(error)) {
        return;
      }
      setFailure({
        message: describeError(error),
        retryJobId: error instanceof IngestJobFailureError ? error.job.id : null,
      });
      setPhase("idle");
      return;
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    }

    if (generation !== runGeneration.current || file === null) {
      return;
    }
    setPhase("idle");
    onReadyRef.current(file);
  };

  const start = (enqueue: () => Promise<IngestJobSchema>) => {
    const generation = runGeneration.current + 1;
    runGeneration.current = generation;
    setFailure(null);
    setJob(null);
    setPhase("enqueueing");
    void (async () => {
      try {
        const queued = await enqueue();
        if (generation !== runGeneration.current) {
          return;
        }
        setJob(queued);
        setPhase("processing");
        await followJob(generation, queued.id);
      } catch (error) {
        if (generation !== runGeneration.current || isAbortError(error)) {
          return;
        }
        setFailure({ message: describeError(error), retryJobId: null });
        setPhase("idle");
      }
    })();
  };

  const cancel = () => {
    runGeneration.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
    setPhase("idle");
  };

  const reset = () => {
    setFailure(null);
    setJob(null);
    setPhase("idle");
  };

  return { phase, job, failure, start, cancel, reset };
}
