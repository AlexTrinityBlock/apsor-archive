/**
 * Companion preference model and its local store. The store is a tiny
 * external store so the chat overlay and the settings panel stay in sync, and
 * so other tabs follow through the `storage` event.
 */
import { readJson, storageKeyMatches, writeJson } from "./storage";

export type CompanionMotion = "full" | "reduced" | "off";

export interface CompanionPreference {
  readonly enabled: boolean;
  /** Preset id or `custom-<id>`; null means the first available preset. */
  readonly companionId: string | null;
  readonly motion: CompanionMotion;
}

export const DEFAULT_PREFERENCE: CompanionPreference = {
  enabled: true,
  companionId: null,
  motion: "full",
};

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
