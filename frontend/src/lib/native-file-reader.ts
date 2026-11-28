import type * as PptxViewerExports from "pptxviewjs";

/**
 * Guards the browser's native `FileReader` against third-party overrides.
 *
 * `pptxviewjs` assigns its own class to `window.FileReader` when its bundle
 * evaluates. `docx-preview` then calls `readAsDataURL` on that class and fails,
 * so embedded DOCX images and fonts break for the rest of the tab once any
 * PPTX preview or thumbnail has loaded. The native constructor is captured when
 * this module first evaluates (it is imported from `main.tsx`, before any lazy
 * chunk) and put back after every PPTX import/render and before every DOCX
 * render.
 */

type PptxViewerModule = typeof PptxViewerExports;

export type FileReaderHost = { FileReader?: unknown };

export interface FileReaderGuard {
  /** Put the captured constructor back; returns whether it had been replaced. */
  readonly restore: () => boolean;
}

/** Capture `host.FileReader` now and return a guard that can restore it. */
export function createFileReaderGuard(host: FileReaderHost | undefined): FileReaderGuard {
  const native = host?.FileReader;
  return {
    restore: () => {
      if (!host || native === undefined || host.FileReader === native) {
        return false;
      }
      host.FileReader = native;
      return true;
    },
  };
}

const guard = createFileReaderGuard(
  typeof globalThis === "undefined" ? undefined : (globalThis as FileReaderHost),
);

/** Put the browser's native `FileReader` back if something replaced it. */
export function restoreNativeFileReader(): boolean {
  return guard.restore();
}

/** Import `pptxviewjs` without letting it keep its `FileReader` override. */
export async function importPptxViewer(): Promise<PptxViewerModule> {
  try {
    return await import("pptxviewjs");
  } finally {
    restoreNativeFileReader();
  }
}
