/**
 * Canonical Library resource URLs.
 *
 * Folder names are user text and may contain characters that would otherwise
 * split a URL (`?`, `#`, `%`, `&`, `+`, spaces, or non-ASCII). Each path
 * segment is percent-encoded independently, and parsing decodes exactly once
 * and rejects separators or traversal segments. File resources use numeric ids
 * only, so a citation link can never be broken by a file name.
 */

export type LibraryTab = "files" | "media";

export interface LibraryRoute {
  readonly tab: LibraryTab;
  readonly folderPath: string | null;
  readonly fileId: number | null;
}

export interface LegacyLibraryRedirect {
  readonly to: string;
  readonly state?: { readonly libraryFolderPath: string };
}

type QueryValue = string | number | null | undefined;

const LIBRARY_ROOT = "/library";
const MEDIA_ROOT = "/library/media";
const LEGACY_KEYS = ["tab", "path", "file", "media"] as const;
const PRESERVED_LEGACY_KEYS = ["q", "view", "chunk", "mode"] as const;

function withQuery(
  pathname: string,
  params?: Readonly<Record<string, QueryValue>>,
): string {
  if (!params) {
    return pathname;
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function normalizeFolderSegments(value: string): string[] {
  return value.split("/").filter(Boolean);
}

function stripTrailingSlashes(value: string): string {
  let end = value.length;
  while (end > 0 && value[end - 1] === "/") {
    end -= 1;
  }
  return value.slice(0, end);
}

function isUnsafeSegment(segment: string): boolean {
  return (
    segment === "" ||
    segment === "." ||
    segment === ".." ||
    segment.includes("/") ||
    segment.includes("\\") ||
    [...segment].some((character) => {
      const code = character.codePointAt(0) ?? 0;
      return code < 32 || code === 127;
    })
  );
}

/** Encode an archive folder path as one or more URL path segments. */
export function encodeLibraryFolderPath(path: string): string {
  return normalizeFolderSegments(path)
    .map((segment) => encodeURIComponent(segment.normalize("NFC")))
    .join("/");
}

/**
 * Decode a folder path from raw pathname segments. Returns null for malformed
 * escapes, traversal segments, separators hidden inside a segment, or control
 * characters instead of throwing.
 */
export function decodeLibraryFolderSegments(
  segments: readonly string[],
): string | null {
  const names: string[] = [];
  for (const segment of segments) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(segment);
    } catch {
      return null;
    }
    const normalized = decoded.normalize("NFC");
    if (isUnsafeSegment(normalized)) {
      return null;
    }
    names.push(normalized);
  }
  return names.length === 0 ? "/" : `/${names.join("/")}`;
}

function parsePositiveId(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined || !/^[1-9]\d*$/.test(raw)) {
    return null;
  }
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/** True when a pathname belongs to the Library workspace. */
export function isLibraryPath(pathname: string): boolean {
  return pathname === LIBRARY_ROOT || pathname.startsWith(`${LIBRARY_ROOT}/`);
}

/**
 * Parse a canonical Library pathname.
 *
 * `/library` and `/library/media` are the two collection roots.
 * `/library/folders/...` and `/library/media/folders/...` address folders by
 * encoded archive path. `/library/files/:id` and
 * `/library/media/files/:id` address one file.
 */
export function parseLibraryUrl(pathname: string): LibraryRoute | null {
  if (!isLibraryPath(pathname)) {
    return null;
  }
  const tail = pathname.slice(LIBRARY_ROOT.length);
  if (tail === "" || tail === "/") {
    return { tab: "files", folderPath: "/", fileId: null };
  }
  if (!tail.startsWith("/")) {
    return null;
  }

  const rawSegments = stripTrailingSlashes(tail.slice(1)).split("/");
  if (rawSegments.some((segment) => segment === "")) {
    return null;
  }

  let tab: LibraryTab = "files";
  let segments = rawSegments;
  if (segments[0] === "media") {
    tab = "media";
    segments = segments.slice(1);
    if (segments.length === 0) {
      return { tab, folderPath: "/", fileId: null };
    }
  }

  if (segments[0] === "folders") {
    if (segments.length === 1) {
      return null;
    }
    const folderPath = decodeLibraryFolderSegments(segments.slice(1));
    return folderPath === null ? null : { tab, folderPath, fileId: null };
  }

  if (segments[0] === "files" && segments.length === 2) {
    const fileId = parsePositiveId(segments[1]);
    return fileId === null ? null : { tab, folderPath: null, fileId };
  }

  return null;
}

/** Build the canonical URL for one archive folder. */
export function libraryFolderUrl(
  path: string,
  tab: LibraryTab = "files",
  params?: Readonly<Record<string, QueryValue>>,
): string {
  const base = tab === "media" ? MEDIA_ROOT : LIBRARY_ROOT;
  const encoded = encodeLibraryFolderPath(path);
  const pathname = encoded.length > 0 ? `${base}/folders/${encoded}` : base;
  return withQuery(pathname, params);
}

/** Build the canonical URL for one file resource. */
export function libraryFileUrl(
  fileId: number,
  tab: LibraryTab = "files",
  params?: Readonly<Record<string, QueryValue>>,
): string {
  const base = tab === "media" ? `${MEDIA_ROOT}/files` : `${LIBRARY_ROOT}/files`;
  return withQuery(`${base}/${fileId}`, params);
}

function normalizeLegacyFolderPath(raw: string | null): string {
  if (!raw) {
    return "/";
  }
  const names = normalizeFolderSegments(raw).map((segment) =>
    segment.normalize("NFC"),
  );
  if (names.some(isUnsafeSegment)) {
    return "/";
  }
  return names.length === 0 ? "/" : `/${names.join("/")}`;
}

/**
 * Canonicalize a legacy `/library?...` link. Old citations used
 * `?tab=files&file=123&chunk=2`, and folder links used `?path=/a/b`.
 *
 * Returns null when the location is not a legacy Library URL, so canonical
 * paths render without a redirect.
 */
export function legacyLibraryRedirect(
  pathname: string,
  search: string,
): LegacyLibraryRedirect | null {
  if (pathname !== LIBRARY_ROOT && pathname !== `${LIBRARY_ROOT}/`) {
    return null;
  }
  const params = new URLSearchParams(search);
  if (!LEGACY_KEYS.some((key) => params.has(key))) {
    return null;
  }

  const tab: LibraryTab = params.get("tab") === "media" ? "media" : "files";
  const idSource =
    tab === "media"
      ? params.get("media") ?? params.get("file")
      : params.get("file");
  const fileId = parsePositiveId(idSource);
  const folderPath = normalizeLegacyFolderPath(params.get("path"));

  const preserved: Record<string, string> = {};
  for (const key of PRESERVED_LEGACY_KEYS) {
    const value = params.get(key);
    if (value !== null && value.length > 0) {
      preserved[key] = value;
    }
  }

  if (fileId !== null) {
    const to = libraryFileUrl(fileId, tab, preserved);
    return folderPath === "/"
      ? { to }
      : { to, state: { libraryFolderPath: folderPath } };
  }

  return { to: libraryFolderUrl(folderPath, tab, preserved) };
}

/* --------------------------------------------------------------------------
   Memories: the Library's third collection. Memories have no folders, so they
   are addressed separately from `LibraryTab` and its folder/file builders.
   -------------------------------------------------------------------------- */

export const LIBRARY_MEMORIES_ROOT = "/library/memories";
const LEGACY_MEMORY_ROOT = "/memory";

export type LibraryMemoryRoute =
  | { readonly kind: "index" }
  | { readonly kind: "new" }
  | { readonly kind: "read"; readonly rawId: string };

/** Build the Memories collection URL, optionally with `q` / `status`. */
export function libraryMemoriesUrl(
  params?: Readonly<Record<string, QueryValue>>,
): string {
  return withQuery(LIBRARY_MEMORIES_ROOT, params);
}

/** Build the canonical reader URL for one memory. */
export function libraryMemoryUrl(
  memoryId: number | string,
  params?: Readonly<Record<string, QueryValue>>,
): string {
  return withQuery(
    `${LIBRARY_MEMORIES_ROOT}/${encodeURIComponent(String(memoryId))}`,
    params,
  );
}

/** Build the new-memory URL; every superseded id is kept as its own param. */
export function libraryNewMemoryUrl(supersedes: readonly number[] = []): string {
  const search = new URLSearchParams();
  for (const id of supersedes) {
    search.append("supersedes", String(id));
  }
  const query = search.toString();
  return query
    ? `${LIBRARY_MEMORIES_ROOT}/new?${query}`
    : `${LIBRARY_MEMORIES_ROOT}/new`;
}

/**
 * Parse `/library/memories`, `/library/memories/new`, and
 * `/library/memories/:id`. The reader keeps the raw id so an invalid id still
 * renders the "memory missing" state instead of silently redirecting.
 */
export function parseLibraryMemoryUrl(
  pathname: string,
): LibraryMemoryRoute | null {
  if (
    pathname !== LIBRARY_MEMORIES_ROOT &&
    !pathname.startsWith(`${LIBRARY_MEMORIES_ROOT}/`)
  ) {
    return null;
  }
  const tail = stripTrailingSlashes(pathname.slice(LIBRARY_MEMORIES_ROOT.length));
  if (tail === "") {
    return { kind: "index" };
  }
  const segments = tail.slice(1).split("/");
  if (segments.length !== 1 || segments[0] === "") {
    return null;
  }
  if (segments[0] === "new") {
    return { kind: "new" };
  }
  let rawId: string;
  try {
    rawId = decodeURIComponent(segments[0]);
  } catch {
    rawId = segments[0];
  }
  return { kind: "read", rawId };
}

/**
 * Map a legacy `/memory`, `/memory/new`, or `/memory/:id` URL to its Library
 * location, keeping the query string (including repeated `supersedes`).
 * Returns null for any other pathname.
 */
export function legacyMemoryRedirect(
  pathname: string,
  search: string,
): string | null {
  if (
    pathname !== LEGACY_MEMORY_ROOT &&
    !pathname.startsWith(`${LEGACY_MEMORY_ROOT}/`)
  ) {
    return null;
  }
  const tail = stripTrailingSlashes(pathname.slice(LEGACY_MEMORY_ROOT.length));
  const query = search.startsWith("?") ? search.slice(1) : search;
  const suffix = query ? `?${query}` : "";
  return `${LIBRARY_MEMORIES_ROOT}${tail}${suffix}`;
}
