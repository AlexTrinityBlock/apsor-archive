// @ts-expect-error -- `bun:test` is provided by the Bun runtime; the frontend tsconfig does not load @types/bun.
import { describe, expect, test } from "bun:test";

import {
  isAcceptedFileName,
  planUploadTargets,
  uniqueArchivePath,
} from "./library-utils";

describe("uniqueArchivePath", () => {
  test("keeps a free name unchanged", () => {
    expect(
      uniqueArchivePath("/docs", "report.pdf", new Set(["/docs/other.pdf"])),
    ).toEqual({ fileName: "report.pdf", path: "/docs/report.pdf" });
  });

  test("adds the first free numeric suffix before the extension", () => {
    expect(
      uniqueArchivePath("/docs", "report.pdf", new Set(["/docs/report.pdf"])),
    ).toEqual({ fileName: "report (1).pdf", path: "/docs/report (1).pdf" });

    expect(
      uniqueArchivePath(
        "/docs",
        "report.pdf",
        new Set(["/docs/report.pdf", "/docs/report (1).pdf"]),
      ),
    ).toEqual({ fileName: "report (2).pdf", path: "/docs/report (2).pdf" });
  });

  test("keeps a duplicate dotfile's accepted suffix", () => {
    const result = uniqueArchivePath("/", ".env", new Set(["/.env"]));

    expect(result).toEqual({
      fileName: "copy (1).env",
      path: "/copy (1).env",
    });
    expect(isAcceptedFileName(result.fileName)).toBe(true);
  });

  test("keeps extensionless names readable", () => {
    expect(
      uniqueArchivePath("/notes", "README", new Set(["/notes/README"])),
    ).toEqual({ fileName: "README (1)", path: "/notes/README (1)" });
  });

  test("only considers paths inside the target folder", () => {
    expect(
      uniqueArchivePath(
        "/docs",
        "report.pdf",
        new Set(["/archive/report.pdf", "/docs/other/report.pdf"]),
      ),
    ).toEqual({ fileName: "report.pdf", path: "/docs/report.pdf" });
  });
});

describe("isAcceptedFileName", () => {
  test("accepts structured text and dotfiles", () => {
    for (const name of [
      "events.jsonl",
      "settings.toml",
      "settings.ini",
      ".env",
      "report.csv",
      "notes.md",
      "data.json",
    ]) {
      expect(isAcceptedFileName(name)).toBe(true);
    }
  });

  test("still rejects unsupported archives", () => {
    expect(isAcceptedFileName("deck.ppt")).toBe(false);
    expect(isAcceptedFileName("budget.numbers")).toBe(false);
  });
});

describe("planUploadTargets", () => {
  test("renames duplicates inside one paste in order", () => {
    const files = [
      new File(["one"], "shot.png", { type: "image/png" }),
      new File(["two"], "shot.png", { type: "image/png" }),
    ];

    const plan = planUploadTargets(files, "/pics", new Set(["/pics/shot.png"]));

    expect(plan.map((item) => item.fileName)).toEqual([
      "shot (1).png",
      "shot (2).png",
    ]);
    expect(plan.map((item) => item.targetPath)).toEqual([
      "/pics/shot (1).png",
      "/pics/shot (2).png",
    ]);
    expect(plan[0].file).toBe(files[0]);
    expect(plan[0].file.size).toBe(3);
    expect(plan[0].file.type).toBe("image/png");
  });

  test("keeps every dotfile in one paste accepted", () => {
    const files = [
      new File(["one"], ".env", { type: "text/plain" }),
      new File(["two"], ".env", { type: "text/plain" }),
      new File(["three"], ".env", { type: "text/plain" }),
    ];

    const plan = planUploadTargets(files, "/", new Set());

    expect(plan.map((item) => item.fileName)).toEqual([
      ".env",
      "copy (1).env",
      "copy (2).env",
    ]);
    expect(plan.every((item) => isAcceptedFileName(item.fileName))).toBe(true);
  });

  test("keeps free files byte-for-byte and does not mutate the taken set", () => {
    const file = new File(["notes"], "notes.txt", { type: "text/plain" });
    const taken = new Set(["/docs/other.txt"]);

    const plan = planUploadTargets([file], "/docs", taken);

    expect(plan).toEqual([
      { file, fileName: "notes.txt", targetPath: "/docs/notes.txt" },
    ]);
    expect(taken).toEqual(new Set(["/docs/other.txt"]));
  });
});
