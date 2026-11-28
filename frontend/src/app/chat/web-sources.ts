/**
 * Web sources cited as `[web:wN]`. The backend numbers every web page a
 * conversation saw; the chat resolves a number to its URL and title from
 * `listAgentWebSources`, falling back to the tool results already loaded in
 * the transcript (forks and saved answers carry their own copies there).
 */
import { createContext, useContext } from "react";

import type { AgentEntrySchema } from "../generated-apis-types/schemas";

export interface WebSource {
  readonly url: string;
  readonly title: string | null;
}

export type WebSourceMap = ReadonlyMap<number, WebSource>;

const EMPTY: WebSourceMap = new Map();

export const WebSourcesContext = createContext<WebSourceMap>(EMPTY);

/** The web sources of the conversation being read; empty outside a chat. */
export function useWebSources(): WebSourceMap {
  return useContext(WebSourcesContext);
}

/** Parse `w3` into 3; anything else is `null`. */
export function webRefNumber(ref: unknown): number | null {
  if (typeof ref !== "string") {
    return null;
  }
  const match = /^w([1-9]\d{0,8})$/.exec(ref.trim());
  return match ? Number(match[1]) : null;
}

/** Only absolute http(s) URLs are ever opened. */
export function safeWebUrl(url: unknown): string | null {
  if (typeof url !== "string") {
    return null;
  }
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

/** A short, favicon-free label: the host without a leading `www.`. */
export function webDomainLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return url;
  }
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function add(
  map: Map<number, WebSource>,
  ref: unknown,
  url: unknown,
  title: unknown,
): void {
  const number = webRefNumber(ref);
  const safe = safeWebUrl(url);
  if (number === null || safe === null) {
    return;
  }
  const existing = map.get(number);
  const cleanTitle =
    typeof title === "string" && title.trim().length > 0 ? title.trim() : null;
  if (!existing || (existing.title === null && cleanTitle !== null)) {
    map.set(number, { url: safe, title: cleanTitle ?? existing?.title ?? null });
  }
}

function collect(
  map: Map<number, WebSource>,
  tool: unknown,
  data: Record<string, unknown> | null,
): void {
  if (!data) {
    return;
  }
  if (tool === "web_search" && Array.isArray(data.results)) {
    for (const item of data.results) {
      const hit = record(item);
      if (hit) {
        add(map, hit.ref, hit.url, hit.title);
      }
    }
  } else if (tool === "web_fetch") {
    add(map, data.ref, data.url, null);
  }
}

/**
 * Collect `[web:wN]` targets from loaded web_search / web_fetch tool results,
 * including the live run's tool steps so a streaming answer resolves at once.
 */
export function webSourcesFromEntries(
  entries: readonly AgentEntrySchema[],
  liveTools: readonly { readonly name: string; readonly data: unknown }[] = [],
): Map<number, WebSource> {
  const map = new Map<number, WebSource>();
  for (const entry of entries) {
    if (entry.kind !== "pi.tool-result") {
      continue;
    }
    const data = record(entry.data);
    collect(map, data?.tool, data);
  }
  for (const tool of liveTools) {
    collect(map, tool.name, record(tool.data));
  }
  return map;
}

/** Server rows win; transcript rows fill the gaps (and old forks). */
export function mergeWebSources(
  server: readonly { ref: string; url: string; title?: string | null }[],
  fromEntries: Map<number, WebSource>,
): WebSourceMap {
  const merged = new Map(fromEntries);
  for (const row of server) {
    const number = webRefNumber(row.ref);
    const safe = safeWebUrl(row.url);
    if (number !== null && safe !== null) {
      merged.set(number, {
        url: safe,
        title: row.title ?? merged.get(number)?.title ?? null,
      });
    }
  }
  return merged;
}
