/**
 * Copy PDF.js CMaps and standard fonts into the Vite public directory.
 *
 * PDF.js loads these as runtime URLs, so they must sit beside the built app
 * rather than inside the JavaScript bundle. They are generated from the pinned
 * pdfjs-dist package into the gitignored public directory; Vite emits them into
 * dist/pdfjs, which is committed because the Docker image copies dist directly.
 */
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(root, "node_modules", "pdfjs-dist");
const target = resolve(root, "public", "pdfjs");

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(resolve(source, "cmaps"), resolve(target, "cmaps"), { recursive: true });
cpSync(resolve(source, "standard_fonts"), resolve(target, "standard_fonts"), {
  recursive: true,
});
