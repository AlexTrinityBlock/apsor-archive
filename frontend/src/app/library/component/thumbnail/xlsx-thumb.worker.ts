import { read, type WorkBook } from "xlsx";

import { XLSX_READ_OPTIONS } from "../../../viewer/component/xlsx-options";
import {
  buildXlsxThumbSheet,
  type XlsxThumbWorkerMessage,
} from "./xlsx-thumb-grid";

interface WorkerScope {
  onmessage: ((event: MessageEvent<ArrayBuffer>) => void) | null;
  postMessage: (message: XlsxThumbWorkerMessage) => void;
}

const workerScope = self as unknown as WorkerScope;

function postError(error: unknown): void {
  const message =
    error instanceof Error && error.message.length > 0
      ? error.message
      : "Unable to parse the workbook";
  workerScope.postMessage({ type: "error", message });
}

/**
 * Parse one workbook away from the UI thread.
 *
 * The main thread transfers the original bytes and receives only the bounded
 * excerpt the canvas needs. SheetJS itself never enters the library page's
 * module graph; this worker owns the import.
 */
workerScope.onmessage = (event: MessageEvent<ArrayBuffer>) => {
  try {
    const workbook: WorkBook = read(
      new Uint8Array(event.data),
      XLSX_READ_OPTIONS,
    );
    workerScope.postMessage({ type: "ok", sheet: buildXlsxThumbSheet(workbook) });
  } catch (error) {
    postError(error);
  }
};
