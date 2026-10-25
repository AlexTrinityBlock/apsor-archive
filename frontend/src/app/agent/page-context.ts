/**
 * Plain-text page snapshots for the persistent agent.
 *
 * The snapshot is deliberately DOM-derived, not model-authored: it walks the
 * visible text of `#main-content`, skips chrome and controls, and caps the
 * result at the same 6,000 characters the backend stores. The page key is
 * stable for a location and changes only when a meaningful archive parameter
 * changes, so repeated questions from one page reuse the same context entry.
 */
import type { AgentEntrySchema } from "../generated-apis-types/schemas";
import { getActiveLocale, translate } from "../i18n";
import { isRecord, type JsonRecord } from "../chat/types";

export const MAX_PAGE_CONTEXT_CHARS = 6_000;

const MAX_KEY_CHARS = 512;
const MAX_PATH_CHARS = 1_024;
const MAX_TITLE_CHARS = 300;

const MEANINGFUL_PARAMS = [
  "path",
  "file",
  "chunk",
  "q",
  "query",
  "result_number",
  "include_history",
  "year",
  "month",
  "day",
  "range",
  "root",
  "depth",
  "history",
  "supersedes",
] as const;

const BLOCK_TAGS = new Set([
  "ADDRESS",
  "ARTICLE",
  "ASIDE",
  "BLOCKQUOTE",
  "DD",
  "DETAILS",
  "DIV",
  "DL",
  "DT",
  "FIGCAPTION",
  "FIGURE",
  "FOOTER",
  "FORM",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HEADER",
  "HR",
  "LI",
  "MAIN",
  "OL",
  "P",
  "PRE",
  "SECTION",
  "SUMMARY",
  "TABLE",
  "TBODY",
  "TD",
  "TH",
  "THEAD",
  "TR",
  "UL",
]);

const EXCLUDED_TAGS = new Set([
  "AUDIO",
  "BUTTON",
  "CANVAS",
  "INPUT",
  "NAV",
  "NOSCRIPT",
  "OPTION",
  "SCRIPT",
  "SELECT",
  "STYLE",
  "SVG",
  "TEMPLATE",
  "TEXTAREA",
  "VIDEO",
]);

const EXCLUDED_SELECTOR = [
  "[aria-hidden='true']",
  "[data-agent-surface]",
  "[data-page-context='exclude']",
  "[hidden]",
  ".pi-agent-root",
  ".pi-agent-overlay",
  ".pi-agent-panel",
  ".pi-agent-workspace",
  ".skip-link",
  ".visually-hidden",
].join(",");

export interface PageContextSnapshot {
  readonly key: string;
  readonly path: string;
  readonly title: string | null;
  readonly text: string;
  readonly truncated: boolean;
}

export interface PersistedPageContext {
  readonly key: string;
  readonly path: string;
  readonly title: string | null;
  readonly text: string;
  readonly textChars: number;
  readonly truncated: boolean;
}

/** True when the dock should not capture the page (the full desk itself). */
export function isChatPath(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}

/** The canonical, meaningful part of a query string for page identity. */
export function canonicalPageSearch(search: string): string {
  const source = new URLSearchParams(search);
  const canonical = new URLSearchParams();
  for (const key of MEANINGFUL_PARAMS) {
    const value = source.get(key);
    if (value !== null && value.length > 0) {
      canonical.set(key, value);
    }
  }
  return canonical.toString();
}

function hashKey(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
}

/** A stable page identity derived from the path and meaningful parameters. */
export function pageContextKey(pathname: string, search: string): string {
  const canonical = canonicalPageSearch(search);
  const suffix = canonical.length > 0 ? "?" + canonical : "";
  const raw = "v1:" + pathname + suffix;
  if (raw.length <= MAX_KEY_CHARS) {
    return raw;
  }
  return "v1:#" + hashKey(raw);
}

/** A human-readable path label that still changes with meaningful params. */
export function pageContextPath(pathname: string, search: string): string {
  const canonical = canonicalPageSearch(search);
  const suffix = canonical.length > 0 ? "?" + canonical : "";
  const raw = pathname + suffix;
  return raw.length <= MAX_PATH_CHARS ? raw : raw.slice(0, MAX_PATH_CHARS - 1) + "…";
}

function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function isExcludedElement(element: Element): boolean {
  if (EXCLUDED_TAGS.has(element.tagName)) {
    return true;
  }
  if (element.matches(EXCLUDED_SELECTOR)) {
    return true;
  }
  const style = window.getComputedStyle(element);
  return (
    style.display === "none" ||
    style.visibility === "hidden" ||
    style.contentVisibility === "hidden"
  );
}

function pushText(node: Text, chunks: string[]): void {
  if (!node.nodeValue) {
    return;
  }
  const text = compact(node.nodeValue);
  if (text.length > 0) {
    chunks.push(text);
  }
}

function walk(node: Node, chunks: string[]): void {
  if (node.nodeType === Node.TEXT_NODE) {
    pushText(node as Text, chunks);
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return;
  }
  const element = node as Element;
  if (isExcludedElement(element)) {
    return;
  }
  const block = BLOCK_TAGS.has(element.tagName);
  if (block) {
    chunks.push("\n");
  }
  for (const child of element.childNodes) {
    walk(child, chunks);
  }
  if (block) {
    chunks.push("\n");
  }
}

/** Normalize captured fragments without losing paragraph boundaries. */
export function normalizePageText(chunks: readonly string[]): string {
  const lines: string[] = [];
  for (const rawLine of chunks.join(" ").split(/\r?\n/)) {
    const line = rawLine.split(/[ \t]+/).filter(Boolean).join(" ");
    if (line.length === 0) {
      if (lines.length > 0 && lines[lines.length - 1] !== "") {
        lines.push("");
      }
    } else {
      lines.push(line);
    }
  }
  return lines.join("\n").trim();
}

function readableTitle(root: HTMLElement, pathname: string): string | null {
  const heading = root.querySelector("h1, h2");
  const text = heading ? compact(heading.textContent ?? "") : "";
  if (text.length > 0) {
    return text.slice(0, MAX_TITLE_CHARS);
  }
  const label = pathname
    .split("/")
    .filter(Boolean)
    .join(" ")
    .replace(/[-_]+/g, " ");
  return (
    label.length > 0
      ? label
      : translate(getActiveLocale(), "chat.pageContext.archiveTitle")
  ).slice(0, MAX_TITLE_CHARS);
}

/**
 * Capture the visible plain text of the current main column.
 *
 * Returns `null` when there is no main region (viewer routes and the full
 * `/chat` desk deliberately do not produce page context).
 */
export function capturePageContext(
  pathname: string,
  search: string,
): PageContextSnapshot | null {
  if (isChatPath(pathname) || typeof document === "undefined") {
    return null;
  }
  const root = document.getElementById("main-content");
  if (!root) {
    return null;
  }

  const chunks: string[] = [];
  for (const child of root.childNodes) {
    walk(child, chunks);
  }
  const normalized = normalizePageText(chunks);
  if (normalized.length === 0) {
    return null;
  }

  const truncated = normalized.length > MAX_PAGE_CONTEXT_CHARS;
  const text = truncated
    ? normalized.slice(0, MAX_PAGE_CONTEXT_CHARS).trimEnd()
    : normalized;

  return {
    key: pageContextKey(pathname, search),
    path: pageContextPath(pathname, search),
    title: readableTitle(root, pathname),
    text,
    truncated,
  };
}

function asRecord(value: unknown): JsonRecord | null {
  return isRecord(value) ? value : null;
}

function stringField(record: JsonRecord | null, key: string): string | null {
  const value = record?.[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function numberField(record: JsonRecord | null, key: string): number | null {
  const value = record?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function decodeXmlText(value: string): string {
  if (typeof DOMParser === "undefined") {
    return value;
  }
  try {
    const doc = new DOMParser().parseFromString(
      `<root>${value}</root>`,
      "application/xml",
    );
    return doc.documentElement.textContent ?? "";
  } catch {
    return value;
  }
}

function envelopeText(content: string): string {
  const match = /<text>([\s\S]*?)<\/text>/i.exec(content);
  return match ? decodeXmlText(match[1]) : "";
}

/** Read the captured text from the provider-facing envelope in the entry model. */
export function pageContextEntryText(entry: AgentEntrySchema): string {
  const message = entry.model?.find((item) => item.role === "user");
  const content = message?.content;
  if (typeof content !== "string" || content.length === 0) {
    return "";
  }
  if (typeof DOMParser === "undefined") {
    return envelopeText(content);
  }
  try {
    const doc = new DOMParser().parseFromString(content, "application/xml");
    if (doc.querySelector("parsererror")) {
      return envelopeText(content);
    }
    const text = doc.querySelector("page_context > text")?.textContent ?? "";
    return text.trim();
  } catch {
    return envelopeText(content);
  }
}

/** True for the append-only page snapshot entry kind. */
export function isPageContextEntry(entry: AgentEntrySchema): boolean {
  return entry.kind === "pi.page-context";
}

/** Narrow one persisted `pi.page-context` entry for the transcript card. */
export function readPageContextEntry(
  entry: AgentEntrySchema,
): PersistedPageContext | null {
  if (!isPageContextEntry(entry)) {
    return null;
  }
  const data = asRecord(entry.data);
  const key = stringField(data, "page_key");
  const path = stringField(data, "path");
  if (!key || !path) {
    return null;
  }
  const text = pageContextEntryText(entry).trim();
  const textChars = numberField(data, "text_chars") ?? text.length;
  return {
    key,
    path,
    title: stringField(data, "title"),
    text,
    textChars,
    truncated: data?.truncated === true,
  };
}
