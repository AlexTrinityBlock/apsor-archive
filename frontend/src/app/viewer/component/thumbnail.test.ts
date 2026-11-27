// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import { readResource } from "../../chat/types";
import { previewBoxWidth } from "../../chat/component/resource-frame";
import {
  fileThumbnailUrl,
  readThumbnail,
  thumbnailAspect,
  thumbnailPageRatio,
} from "./thumbnail";

const THUMBNAIL = { version: "0123456789abcdef", width: 320, height: 160 };

describe("readThumbnail", () => {
  test("accepts a well-formed thumbnail", () => {
    expect(readThumbnail(THUMBNAIL)).toEqual(THUMBNAIL);
  });

  test("rejects missing, malformed, or out-of-range values", () => {
    expect(readThumbnail(null)).toBeNull();
    expect(readThumbnail("thumb")).toBeNull();
    expect(readThumbnail({ ...THUMBNAIL, version: "../x" })).toBeNull();
    expect(readThumbnail({ ...THUMBNAIL, width: 0 })).toBeNull();
    expect(readThumbnail({ ...THUMBNAIL, height: 9999 })).toBeNull();
    expect(readThumbnail({ ...THUMBNAIL, width: 12.5 })).toBeNull();
  });
});

describe("thumbnail sizing", () => {
  test("derives the CSS aspect ratio and page ratio", () => {
    expect(thumbnailAspect(THUMBNAIL)).toBe("320 / 160");
    expect(thumbnailPageRatio({ ...THUMBNAIL, width: 240, height: 320 })).toBeCloseTo(4 / 3);
  });

  test("fits landscape and portrait previews into the 420px box", () => {
    expect(previewBoxWidth(THUMBNAIL)).toBe(420);
    expect(previewBoxWidth({ ...THUMBNAIL, width: 247, height: 320 })).toBe(324);
  });

  test("builds a versioned thumbnail URL", () => {
    expect(fileThumbnailUrl(12, "abc")).toBe("/api/v1/files/12/thumbnail?v=abc");
  });
});

describe("readResource thumbnail", () => {
  const base = {
    resource_type: "file",
    resource_id: 7,
    viewer_url: "/viewer/file/7",
    title: "photo.png",
    mime_type: "image/png",
    raw_file_path: "/photos/photo.png",
    chunk: null,
  };

  test("parses a presented thumbnail", () => {
    expect(readResource({ ...base, thumbnail: THUMBNAIL })?.thumbnail).toEqual(THUMBNAIL);
  });

  test("older transcripts without a thumbnail still parse", () => {
    expect(readResource(base)?.thumbnail).toBeNull();
  });
});
