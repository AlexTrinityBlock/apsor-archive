/**
 * The companion data layer. Everything the overlay and the settings panel
 * read or write goes through these hooks, so wiring the generated Orval client
 * (listCompanions, createCompanion, uploadCompanionFrames, …,
 * getCompanionPreference, updateCompanionPreference) is a change to this file
 * only.
 *
 * Until that client exists:
 * - preferences live in the per-account local store (`preference.ts`);
 * - built-in presets are static files under `/companions/` (a deliberate
 *   same-origin static-asset fetch, not an API call);
 * - custom companions report `customSupported: false`, and the editor keeps
 *   drafts in memory only;
 * - the story (persona and lore) reports `supported: false`, and the Story
 *   editor keeps edits as a local draft.
 */
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthProvider";
import type { CompanionAction } from "./actions";
import {
  parseManifest,
  parsePresetIndex,
  type CompanionCharacter,
  type CompanionGender,
} from "./manifest";
import {
  preferenceStore,
  type CompanionPreference,
} from "./preference";
import type { CompanionPersona, LoreFragment, LoreInput } from "./story";

const PRESET_ROOT = "/companions";

/** Flip when the backend companion endpoints and generated hooks land. */
export const CUSTOM_COMPANIONS_SUPPORTED = false;

async function loadJson(url: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`companion asset ${response.status}`);
  }
  return (await response.json()) as unknown;
}

/** Load the preset index and every manifest it names; bad entries are skipped. */
export async function loadPresetCharacters(
  signal?: AbortSignal,
): Promise<readonly CompanionCharacter[]> {
  const refs = parsePresetIndex(await loadJson(`${PRESET_ROOT}/index.json`, signal));
  const loaded = await Promise.all(
    refs.map(async (ref) => {
      const base = `${PRESET_ROOT}/${ref.id}`;
      try {
        const character = parseManifest(await loadJson(`${base}/manifest.json`, signal), base);
        if (character === null || character.id !== ref.id) {
          return null;
        }
        return ref.gender !== "unspecified" && character.gender === "unspecified"
          ? { ...character, gender: ref.gender }
          : character;
      } catch {
        return null;
      }
    }),
  );
  return loaded.filter((item): item is CompanionCharacter => item !== null);
}

export const COMPANION_PRESETS_QUERY_KEY = ["companion", "presets"] as const;

export interface CompanionCatalog {
  readonly presets: readonly CompanionCharacter[];
  readonly custom: readonly CompanionCharacter[];
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly refetch: () => void;
  readonly customSupported: boolean;
}

export function useCompanionCatalog(): CompanionCatalog {
  const query = useQuery({
    queryKey: COMPANION_PRESETS_QUERY_KEY,
    queryFn: ({ signal }) => loadPresetCharacters(signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });
  const { refetch } = query;
  return {
    presets: query.data ?? [],
    custom: [],
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: () => void refetch(),
    customSupported: CUSTOM_COMPANIONS_SUPPORTED,
  };
}

function accountKey(userId: number | null | undefined): string {
  return userId === null || userId === undefined ? "anonymous" : `user-${userId}`;
}

export function useCompanionPreference(): readonly [
  CompanionPreference,
  (patch: Partial<CompanionPreference>) => void,
] {
  const { user } = useAuth();
  const store = useMemo(() => preferenceStore(accountKey(user?.user_id)), [user?.user_id]);
  const preference = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const update = useCallback(
    (patch: Partial<CompanionPreference>) => store.update(patch),
    [store],
  );
  return [preference, update] as const;
}

/** Pick the selected character, falling back to the first preset. */
export function selectCharacter(
  catalog: Pick<CompanionCatalog, "presets" | "custom">,
  companionId: string | null,
): CompanionCharacter | null {
  const all = [...catalog.custom, ...catalog.presets];
  return all.find((item) => item.id === companionId) ?? catalog.presets[0] ?? null;
}

export interface CustomCompanionDraft {
  readonly name: string;
  readonly gender: CompanionGender;
  readonly frames: Readonly<Partial<Record<CompanionAction, readonly File[]>>>;
}

/* Story: persona and lore ------------------------------------------------- */

/**
 * Flip when getCompanionPersona / updateCompanionPersona /
 * resetCompanionPersona and listCompanionLore / createCompanionLore /
 * updateCompanionLore / deleteCompanionLore / resetCompanionLore are
 * generated. Rows map through `parseLoreFragment` (server `is_default`,
 * `unlocked`, `unlocked_at`; sealed rows omit `text`).
 */
export const COMPANION_STORY_SUPPORTED = false;

/** Server reference for a companion: `preset:<id>` or `custom:<id>`. */
export type CompanionRef = `preset:${string}` | `custom:${string}`;

const CUSTOM_PREFIX = "custom-";

export function companionRef(character: Pick<CompanionCharacter, "id">): CompanionRef {
  return character.id.startsWith(CUSTOM_PREFIX)
    ? `custom:${character.id.slice(CUSTOM_PREFIX.length)}`
    : `preset:${character.id}`;
}

export interface CompanionStory {
  readonly supported: boolean;
  readonly isLoading: boolean;
  readonly isError: boolean;
  readonly persona: CompanionPersona | null;
  readonly lore: readonly LoreFragment[];
  readonly savePersona: (text: string) => Promise<void>;
  /** Presets only: restore the authored persona. */
  readonly resetPersona: () => Promise<void>;
  readonly createLore: (input: LoreInput) => Promise<void>;
  readonly updateLore: (id: string, input: LoreInput) => Promise<void>;
  readonly deleteLore: (id: string) => Promise<void>;
  /** Restore the authored lore set (presets) or clear it (custom). */
  readonly resetLore: () => Promise<void>;
}

const unavailable = () => Promise.reject(new CompanionApiUnavailableError());

export function useCompanionStory(ref: CompanionRef): CompanionStory {
  return useMemo(
    () => ({
      supported: COMPANION_STORY_SUPPORTED && ref.length > 0,
      isLoading: false,
      isError: false,
      persona: null,
      lore: [],
      savePersona: unavailable,
      resetPersona: unavailable,
      createLore: unavailable,
      updateLore: unavailable,
      deleteLore: unavailable,
      resetLore: unavailable,
    }),
    [ref],
  );
}

export class CompanionApiUnavailableError extends Error {
  constructor() {
    super("custom companions are not available yet");
    this.name = "CompanionApiUnavailableError";
  }
}

export interface CustomCompanionActions {
  readonly supported: boolean;
  /** Create a companion and upload its frames; resolves to the new id. */
  readonly save: (draft: CustomCompanionDraft) => Promise<string>;
  readonly remove: (companionId: string) => Promise<void>;
}

export function useCustomCompanionActions(): CustomCompanionActions {
  return useMemo(
    () => ({
      supported: CUSTOM_COMPANIONS_SUPPORTED,
      save: () => Promise.reject(new CompanionApiUnavailableError()),
      remove: () => Promise.reject(new CompanionApiUnavailableError()),
    }),
    [],
  );
}
