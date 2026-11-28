/**
 * Companion preference model and its local store. The store is a tiny
 * external store so the chat overlay and the settings panel stay in sync, and
 * so other tabs follow through the `storage` event.
 */
import { readJson, storageKeyMatches, writeJson } from "./storage";

export type CompanionMotion = "full" | "reduced" | "off";
/** Display size; `full` shows the art at up to its intrinsic 384×576. */
export type CompanionSize = "compact" | "medium" | "full";
/** How see-through the figure is; `auto` fades only when it is in the way. */
export type CompanionOpacityMode = "opaque" | "translucent" | "auto";

export const COMPANION_SIZES: readonly CompanionSize[] = ["compact", "medium", "full"];
export const COMPANION_OPACITY_MODES: readonly CompanionOpacityMode[] = [
  "opaque",
  "translucent",
  "auto",
];

export interface CompanionPreference {
  readonly enabled: boolean;
  /** Preset id or `custom-<id>`; null means the first available preset. */
  readonly companionId: string | null;
  readonly motion: CompanionMotion;
  readonly size: CompanionSize;
  readonly opacityMode: CompanionOpacityMode;
}

export const DEFAULT_PREFERENCE: CompanionPreference = {
  enabled: true,
  companionId: null,
  motion: "full",
  size: "full",
  opacityMode: "auto",
};

export function readSize(value: unknown): CompanionSize {
  return COMPANION_SIZES.includes(value as CompanionSize) ? (value as CompanionSize) : "full";
}

export function readOpacityMode(value: unknown): CompanionOpacityMode {
  return COMPANION_OPACITY_MODES.includes(value as CompanionOpacityMode)
    ? (value as CompanionOpacityMode)
    : "auto";
}

export function readPreference(value: unknown): CompanionPreference {
  if (typeof value !== "object" || value === null) {
    return DEFAULT_PREFERENCE;
  }
  const record = value as Record<string, unknown>;
  const motion = record.motion;
  return {
    enabled: typeof record.enabled === "boolean" ? record.enabled : DEFAULT_PREFERENCE.enabled,
    companionId:
      typeof record.companionId === "string" && record.companionId.length <= 80
        ? record.companionId
        : null,
    motion: motion === "reduced" || motion === "off" || motion === "full" ? motion : "full",
    size: readSize(record.size),
    opacityMode: readOpacityMode(record.opacityMode),
  };
}

type Listener = () => void;

/** One store per account key, so accounts sharing a browser stay separate. */
export class PreferenceStore {
  private value: CompanionPreference;
  private readonly listeners = new Set<Listener>();
  private readonly key: string;

  constructor(accountKey: string) {
    this.key = `preference.${accountKey}`;
    this.value = readPreference(readJson(this.key));
  }

  readonly subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    const onStorage = (event: StorageEvent) => {
      if (storageKeyMatches(event.key, this.key)) {
        this.value = readPreference(readJson(this.key));
        listener();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      this.listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  };

  readonly getSnapshot = (): CompanionPreference => this.value;

  update(patch: Partial<CompanionPreference>): void {
    this.value = { ...this.value, ...patch };
    writeJson(this.key, this.value);
    for (const listener of this.listeners) {
      listener();
    }
  }
}

const stores = new Map<string, PreferenceStore>();

export function preferenceStore(accountKey: string): PreferenceStore {
  let store = stores.get(accountKey);
  if (store === undefined) {
    store = new PreferenceStore(accountKey);
    stores.set(accountKey, store);
  }
  return store;
}

/** Combine the account setting with the operating-system motion request. */
export function effectiveMotion(
  preference: CompanionMotion,
  systemReduced: boolean,
): CompanionMotion {
  if (preference === "off") {
    return "off";
  }
  return systemReduced ? "reduced" : preference;
}
