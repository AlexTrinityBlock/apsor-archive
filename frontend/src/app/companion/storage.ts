/**
 * Browser-local companion conveniences (preference fallback and dock
 * positions). Every access is guarded: private windows and blocked storage
 * must leave the companion working with defaults.
 */
import type { Breakpoint, SavedPosition } from "./layout";
import { readSavedPosition } from "./layout";

const PREFIX = "apsor-archive.companion";

export function readJson(key: string): unknown {
  try {
    const raw = window.localStorage.getItem(`${PREFIX}.${key}`);
    return raw === null ? null : (JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(`${PREFIX}.${key}`, JSON.stringify(value));
  } catch {
    // Storage is a convenience; the in-memory value still applies.
  }
}

export function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(`${PREFIX}.${key}`);
  } catch {
    // Ignore blocked storage.
  }
}

export function storageKeyMatches(eventKey: string | null, key: string): boolean {
  return eventKey === `${PREFIX}.${key}`;
}

export function readPosition(breakpoint: Breakpoint): SavedPosition | null {
  return readSavedPosition(readJson(`position.${breakpoint}`));
}

export function writePosition(breakpoint: Breakpoint, position: SavedPosition): void {
  writeJson(`position.${breakpoint}`, position);
}

export function readMinimized(): boolean {
  return readJson("minimized") === true;
}

export function writeMinimized(value: boolean): void {
  writeJson("minimized", value);
}
