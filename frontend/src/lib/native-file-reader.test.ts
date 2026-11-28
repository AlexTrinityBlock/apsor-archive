// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { createFileReaderGuard } from "./native-file-reader";

class NativeReader {}
class LibraryReader {}

describe("createFileReaderGuard", () => {
  test("restores the captured constructor after a library replaces it", () => {
    const host: { FileReader?: unknown } = { FileReader: NativeReader };
    const guard = createFileReaderGuard(host);
    host.FileReader = LibraryReader; // what pptxviewjs does on load
    expect(guard.restore()).toBe(true);
    expect(host.FileReader).toBe(NativeReader);
  });

  test("is a no-op while the native constructor is in place", () => {
    const host: { FileReader?: unknown } = { FileReader: NativeReader };
    const guard = createFileReaderGuard(host);
    expect(guard.restore()).toBe(false);
    expect(host.FileReader).toBe(NativeReader);
  });

  test("does nothing when there was no native constructor", () => {
    const host: { FileReader?: unknown } = {};
    const guard = createFileReaderGuard(host);
    host.FileReader = LibraryReader;
    expect(guard.restore()).toBe(false);
    expect(host.FileReader).toBe(LibraryReader);
  });
});
