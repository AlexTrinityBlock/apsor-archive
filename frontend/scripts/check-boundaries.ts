/**
 * Workspace import boundaries for `src/app/`.
 *
 * Each top-level folder under `src/app/` is a workspace (a route surface such
 * as `library/` or `timeline/`) or a shared area. A workspace may import from
 * shared areas, `src/lib/`, `src/apis/`, and its own files, but not from
 * another workspace. Documented exceptions live in `ALLOWED_EDGES`; remove an
 * entry once the code that needs it is moved to a shared area.
 *
 * Run with `bun run check:boundaries`; it exits non-zero on a new violation.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

const APP_ROOT = resolve(import.meta.dir, "../src/app");

/** Folders any workspace may import from. */
const SHARED_AREAS = new Set([
  "component",
  "hook",
  "type",
  "i18n",
  "generated-apis-types",
  // Supporting domains consumed by several workspaces (see src/app/AGENTS.md).
  "viewer",
  "auth",
  // The floating chat companion: mounted by chat, configured by settings.
  "companion",
]);

/**
 * Known cross-workspace edges, as `from -> to`. Keep this list short and
 * explain each entry; a new edge should usually be a move into a shared area.
 */
const ALLOWED_EDGES = new Set([
  // The agent run inspector and the chat workspace share run types/renderers.
  "agent -> chat",
  "chat -> agent",
  // Saved-question citations reuse the chat citation href builders.
  "questions -> chat",
  // The account detail page hosts root's companion tab (UserCompanionTab) and
  // the directory reuses its pure filter and sparkline helpers.
  "accounts -> companion-admin",
]);

/** Shared areas may still import selected workspace modules. */
const ALLOWED_SHARED_EDGES = new Set([
  // Sign-out clears the remembered chat conversation.
  "auth -> chat",
  // The router and shell compose every workspace.
  "(root) -> *",
]);

/** Static `from "x"`, side-effect `import "x"`, and dynamic `import("x")`. */
const IMPORT_PATTERNS = [
  /\bfrom\s*["']([^"']+)["']/g,
  /\bimport\s*["']([^"']+)["']/g,
  /\bimport\s*\(\s*["']([^"']+)["']/g,
];

function importSpecifiers(source: string): string[] {
  return IMPORT_PATTERNS.flatMap((pattern) =>
    [...source.matchAll(pattern)].map((match) => match[1]),
  );
}

function walk(directory: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      files.push(...walk(path));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      files.push(path);
    }
  }
  return files;
}

/** The top-level `src/app/` folder that owns `path`, or `(root)`. */
function areaOf(path: string): string {
  const parts = relative(APP_ROOT, path).split(sep);
  return parts.length > 1 ? parts[0] : "(root)";
}

const violations: string[] = [];
for (const file of walk(APP_ROOT)) {
  const fromArea = areaOf(file);
  if (fromArea === "generated-apis-types") {
    continue;
  }
  const source = readFileSync(file, "utf8");
  for (const specifier of importSpecifiers(source)) {
    if (!specifier.startsWith(".")) {
      continue;
    }
    const target = resolve(dirname(file), specifier);
    if (!target.startsWith(APP_ROOT + sep)) {
      continue; // src/lib, src/apis, styles
    }
    const toArea = areaOf(target);
    if (toArea === fromArea || toArea === "(root)" || SHARED_AREAS.has(toArea)) {
      continue;
    }
    const edge = `${fromArea} -> ${toArea}`;
    if (ALLOWED_EDGES.has(edge) || ALLOWED_SHARED_EDGES.has(edge)) {
      continue;
    }
    if (fromArea === "(root)" && ALLOWED_SHARED_EDGES.has("(root) -> *")) {
      continue;
    }
    violations.push(`${relative(APP_ROOT, file)}: ${edge} (${specifier})`);
  }
}

if (violations.length > 0) {
  process.stderr.write("Workspace boundary violations:\n");
  for (const violation of violations) {
    process.stderr.write(`  ${violation}\n`);
  }
  process.stderr.write(
    "Move shared code into component/, hook/, or type/, or document the edge in scripts/check-boundaries.ts.\n",
  );
  process.exit(1);
}
process.stdout.write("workspace boundary check passed\n");
