// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { serverThumbnailClass, serverThumbnailFor } from "./server-thumb";

const THUMBNAIL = { version: "0123456789abcdef", width: 320, height: 240 };

describe("serverThumbnailFor", () => {
  test("uses a ready server thumbnail for a stored original", () => {
    expect(serverThumbnailFor({ has_original: true, thumbnail: THUMBNAIL }, false)).toEqual(
      THUMBNAIL,
    );
  });

  test("falls back to the client renderer without a thumbnail", () => {
    expect(serverThumbnailFor({ has_original: true, thumbnail: null }, false)).toBeNull();
    expect(serverThumbnailFor({ has_original: true }, false)).toBeNull();
  });

  test("falls back after the thumbnail failed to load", () => {
    expect(serverThumbnailFor({ has_original: true, thumbnail: THUMBNAIL }, true)).toBeNull();
  });

  test("never paints a thumbnail for a text-only row", () => {
    expect(serverThumbnailFor({ has_original: false, thumbnail: THUMBNAIL }, false)).toBeNull();
  });

  test("rejects malformed thumbnail data", () => {
    const malformed = { version: "<script>", width: 320, height: 240 };
    expect(serverThumbnailFor({ has_original: true, thumbnail: malformed }, false)).toBeNull();
  });
});

describe("serverThumbnailClass", () => {
  test("keeps each kind's card framing", () => {
    expect(serverThumbnailClass("image")).toBe("library-thumb__image");
    expect(serverThumbnailClass("xlsx")).toBe("library-thumb__sheet");
    expect(serverThumbnailClass("pdf")).toBe("library-thumb__document");
    expect(serverThumbnailClass("docx")).toBe("library-thumb__document");
  });
});
