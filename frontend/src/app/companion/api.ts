/**
 * The companion data layer. Everything the overlay and the settings panel
 * read or write goes through these hooks, so wiring the generated Orval client
 * (listCompanions, createCompanion, uploadCompanionFrames, …,
 * getCompanionPreference, updateCompanionPreference) is a change to this file
 * only.
 *
 * - Preferences are stored per account on the server
 *   (getCompanionPreference / updateCompanionPreference); the per-account
 *   local store (`preference.ts`) is only a cache for instant first paint.
 * - Built-in presets are static files under `/companions/` (a deliberate
 *   same-origin static-asset fetch, not an API call).
 * - Custom companions come from listCompanions and are edited through the
 *   create/update/delete/upload/reorder endpoints; their ids are `custom-<id>`
 *   and their frames use the server's versioned `url`.
 * - The story (persona and lore) still reports `supported: false` until the
 *   persona/lore endpoints land; the Story editor keeps edits as a local draft.
 */
import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthProvider";
import {
  createCompanion,
  deleteCompanion,
  deleteCompanionFrame,
  getGetCompanionPreferenceQueryKey,
  getListCompanionsQueryKey,
  reorderCompanionFrames,
  updateCompanion,
  updateCompanionPreference,
  uploadCompanionFrames,
  useGetCompanionPreference,
  useListCompanions,
} from "../generated-apis-types/companions/companions";
import type {
  CompanionPreferenceSchema,
  CompanionSchema,
} from "../generated-apis-types/schemas";
import type { CompanionAction } from "./actions";
import { COMPANION_ACTIONS } from "./actions";
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
export const CUSTOM_COMPANIONS_SUPPORTED = true;

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

const CUSTOM_PREFIX = "custom-";
const CUSTOM_FRAME_SIZE = { width: 384, height: 576 } as const;
const CUSTOM_ANIMATED_FPS = 5;

/**
 * Turn one server companion into a character. Frames are grouped by action in
 * `position` order; a companion without an `idle` pose borrows its first
 * uploaded action, because every fallback chain ends at `idle`.
 */
export function customCharacter(companion: CompanionSchema): CompanionCharacter | null {
  const grouped = new Map<string, { position: number; url: string }[]>();
  for (const frame of companion.frames) {
    const list = grouped.get(frame.action) ?? [];
    list.push({ position: frame.position, url: frame.url });
    grouped.set(frame.action, list);
  }
  const actions: Record<string, { frames: string[]; fps: number; loop: boolean }> = {};
  for (const action of COMPANION_ACTIONS) {
    const frames = (grouped.get(action) ?? [])
      .sort((a, b) => a.position - b.position)
      .map((frame) => frame.url);
    if (frames.length > 0) {
      actions[action] = {
        frames,
        fps: frames.length > 1 ? CUSTOM_ANIMATED_FPS : 0,
        loop: true,
      };
    }
  }
  if (actions.idle === undefined) {
    const first = COMPANION_ACTIONS.find((action) => actions[action] !== undefined);
    if (first === undefined) {
      return null;
    }
    actions.idle = actions[first];
  }
  const sized = companion.frames[0];
  return parseManifest(
    {
      id: `${CUSTOM_PREFIX}${companion.id}`,
      name: companion.name,
      gender: companion.gender,
      size: sized
        ? { width: sized.width, height: sized.height }
        : CUSTOM_FRAME_SIZE,
      // The first idle frame doubles as the picker portrait.
      portrait: actions.idle.frames[0],
      actions,
    },
    "",
  );
}

export function useCompanionCatalog(): CompanionCatalog {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: COMPANION_PRESETS_QUERY_KEY,
    queryFn: ({ signal }) => loadPresetCharacters(signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });
  const customQuery = useListCompanions({
    query: { enabled: CUSTOM_COMPANIONS_SUPPORTED && user !== null && user !== undefined },
  });
  const custom = useMemo(
    () =>
      (customQuery.data?.resources ?? [])
        .map(customCharacter)
        .filter((item): item is CompanionCharacter => item !== null),
    [customQuery.data],
  );
  const { refetch } = query;
  const { refetch: refetchCustom } = customQuery;
  return {
    presets: query.data ?? [],
    custom,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: () => {
      void refetch();
      void refetchCustom();
    },
    customSupported: CUSTOM_COMPANIONS_SUPPORTED,
  };
}

function accountKey(userId: number | null | undefined): string {
  return userId === null || userId === undefined ? "anonymous" : `user-${userId}`;
}

/** Server `selected` (`preset:<id>` / `custom:<id>`) to a character id. */
export function companionIdFromRef(selected: string | null): string | null {
  if (selected === null) {
    return null;
  }
  if (selected.startsWith("preset:")) {
    return selected.slice("preset:".length) || null;
  }
  if (selected.startsWith("custom:")) {
    const id = selected.slice("custom:".length);
    return /^\d+$/.test(id) ? `${CUSTOM_PREFIX}${id}` : null;
  }
  return null;
}

function fromServer(value: CompanionPreferenceSchema): CompanionPreference {
  return {
    enabled: value.enabled,
    companionId: companionIdFromRef(value.selected),
    motion: value.motion,
  };
}

/**
 * The account's companion preference. The local store paints instantly and
 * mirrors the server row once it loads; every change is written to the
 * server, and the cache follows.
 */
export function useCompanionPreference(): readonly [
  CompanionPreference,
  (patch: Partial<CompanionPreference>) => void,
] {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const signedIn = user !== null && user !== undefined;
  const store = useMemo(() => preferenceStore(accountKey(user?.user_id)), [user?.user_id]);
  const preference = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const serverQuery = useGetCompanionPreference({ query: { enabled: signedIn } });
  const server = serverQuery.data;
  useEffect(() => {
    if (server === undefined || server.updated_at === null) {
      return;
    }
    const next = fromServer(server);
    const current = store.getSnapshot();
    if (
      next.enabled !== current.enabled ||
      next.companionId !== current.companionId ||
      next.motion !== current.motion
    ) {
      store.update(next);
    }
  }, [server, store]);
  const update = useCallback(
    (patch: Partial<CompanionPreference>) => {
      store.update(patch);
      if (!signedIn) {
        return;
      }
      const body: Parameters<typeof updateCompanionPreference>[0] = {};
      if (patch.enabled !== undefined) {
        body.enabled = patch.enabled;
      }
      if (patch.motion !== undefined) {
        body.motion = patch.motion;
      }
      if (patch.companionId !== undefined) {
        body.selected =
          patch.companionId === null ? null : companionRef({ id: patch.companionId });
      }
      void updateCompanionPreference(body)
        .then((saved) => {
          queryClient.setQueryData(getGetCompanionPreferenceQueryKey(), saved);
        })
        .catch(() => {
          void queryClient.invalidateQueries({
            queryKey: getGetCompanionPreferenceQueryKey(),
          });
        });
    },
    [store, signedIn, queryClient],
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
    super("this companion feature is not available yet");
    this.name = "CompanionApiUnavailableError";
  }
}

/** Numeric server id of a `custom-<id>` character, or null for presets. */
export function customCompanionId(companionId: string): number | null {
  if (!companionId.startsWith(CUSTOM_PREFIX)) {
    return null;
  }
  const raw = companionId.slice(CUSTOM_PREFIX.length);
  return /^\d+$/.test(raw) ? Number(raw) : null;
}

function requireCustomId(companionId: string): number {
  const id = customCompanionId(companionId);
  if (id === null) {
    throw new Error("not a custom companion");
  }
  return id;
}

export interface CustomCompanionActions {
  readonly supported: boolean;
  /** Create a companion and upload its frames; resolves to the new id. */
  readonly save: (draft: CustomCompanionDraft) => Promise<string>;
  readonly remove: (companionId: string) => Promise<void>;
  readonly rename: (
    companionId: string,
    patch: { readonly name?: string; readonly gender?: CompanionGender },
  ) => Promise<void>;
  /** Append more frames to one action of an existing companion. */
  readonly addFrames: (
    companionId: string,
    action: CompanionAction,
    files: readonly File[],
  ) => Promise<void>;
  readonly deleteFrame: (companionId: string, frameId: number) => Promise<void>;
  readonly reorderFrames: (
    companionId: string,
    action: CompanionAction,
    frameIds: readonly number[],
  ) => Promise<void>;
}

function serverGender(gender: CompanionGender): "female" | "male" | "other" {
  return gender === "unspecified" ? "other" : gender;
}

export function useCustomCompanionActions(): CustomCompanionActions {
  const queryClient = useQueryClient();
  return useMemo(() => {
    const refresh = () =>
      queryClient.invalidateQueries({ queryKey: getListCompanionsQueryKey() });
    return {
      supported: CUSTOM_COMPANIONS_SUPPORTED,
      save: async (draft) => {
        const created = await createCompanion({
          name: draft.name,
          gender: serverGender(draft.gender),
        });
        try {
          for (const action of COMPANION_ACTIONS) {
            const files = draft.frames[action];
            if (files !== undefined && files.length > 0) {
              await uploadCompanionFrames(created.id, { action, files: [...files] });
            }
          }
        } finally {
          await refresh();
        }
        return `${CUSTOM_PREFIX}${created.id}`;
      },
      remove: async (companionId) => {
        await deleteCompanion(requireCustomId(companionId));
        await refresh();
      },
      rename: async (companionId, patch) => {
        await updateCompanion(requireCustomId(companionId), {
          ...(patch.name === undefined ? {} : { name: patch.name }),
          ...(patch.gender === undefined ? {} : { gender: serverGender(patch.gender) }),
        });
        await refresh();
      },
      addFrames: async (companionId, action, files) => {
        await uploadCompanionFrames(requireCustomId(companionId), {
          action,
          files: [...files],
        });
        await refresh();
      },
      deleteFrame: async (companionId, frameId) => {
        await deleteCompanionFrame(requireCustomId(companionId), frameId);
        await refresh();
      },
      reorderFrames: async (companionId, action, frameIds) => {
        await reorderCompanionFrames(requireCustomId(companionId), {
          action,
          frame_ids: [...frameIds],
        });
        await refresh();
      },
    };
  }, [queryClient]);
}
