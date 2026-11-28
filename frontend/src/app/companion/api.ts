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
 * - The story (persona and lore) uses the persona and lore endpoints in the
 *   current interface locale.
 */
import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../i18n";
import {
  createCompanion,
  createCompanionLore,
  deleteCompanion,
  deleteCompanionLore,
  deleteCompanionFrame,
  getGetCompanionPersonaQueryKey,
  getGetCompanionPreferenceQueryKey,
  getListCompanionLoreQueryKey,
  getListCompanionsQueryKey,
  reorderCompanionFrames,
  resetCompanionLore,
  resetCompanionPersona,
  updateCompanion,
  updateCompanionLore,
  updateCompanionPersona,
  updateCompanionPreference,
  uploadCompanionFrames,
  useGetCompanionPersona,
  useGetCompanionPreference,
  useListCompanionLore,
  useListCompanions,
} from "../generated-apis-types/companions/companions";
import type {
  CompanionLoreSchema,
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
import { readScale } from "./size";
import {
  preferenceStore,
  readOpacityMode,
  readSize,
  type CompanionPreference,
} from "./preference";
import {
  parseLoreFragment,
  tierToWeight,
  type CompanionPersona,
  type LoreFragment,
  type LoreInput,
} from "./story";

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
    size: readSize(value.size),
    scale: readScale(value.scale),
    opacityMode: readOpacityMode(value.opacity_mode),
  };
}

/**
 * The account's companion preference. The local store paints instantly and
 * mirrors the server row once it loads; every change is written to the
 * server, and the cache follows.
 */
type PreferenceBody = Parameters<typeof updateCompanionPreference>[0];

export interface PreferenceUpdateOptions {
  /**
   * Coalesce rapid changes (keyboard or slider steps) into one server write
   * after this many quiet milliseconds; the local value changes at once.
   */
  readonly deferMs?: number;
}

/** The server body for a local preference change. */
export function preferenceBody(patch: Partial<CompanionPreference>): PreferenceBody {
  const body: PreferenceBody = {};
  if (patch.enabled !== undefined) {
    body.enabled = patch.enabled;
  }
  if (patch.motion !== undefined) {
    body.motion = patch.motion;
  }
  if (patch.size !== undefined) {
    body.size = patch.size;
  }
  if (patch.scale !== undefined) {
    body.scale = patch.scale;
  }
  if (patch.opacityMode !== undefined) {
    body.opacity_mode = patch.opacityMode;
  }
  if (patch.companionId !== undefined) {
    body.selected = patch.companionId === null ? null : companionRef({ id: patch.companionId });
  }
  return body;
}

export function useCompanionPreference(): readonly [
  CompanionPreference,
  (patch: Partial<CompanionPreference>, options?: PreferenceUpdateOptions) => void,
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
      next.motion !== current.motion ||
      next.size !== current.size ||
      next.scale !== current.scale ||
      next.opacityMode !== current.opacityMode
    ) {
      store.update(next);
    }
  }, [server, store]);
  const pending = useRef<PreferenceBody>({});
  const timer = useRef<number | null>(null);
  const flush = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    const body = pending.current;
    pending.current = {};
    if (Object.keys(body).length === 0) {
      return;
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
  }, [queryClient]);
  useEffect(() => flush, [flush]);
  const update = useCallback(
    (patch: Partial<CompanionPreference>, options?: PreferenceUpdateOptions) => {
      store.update(patch);
      if (!signedIn) {
        return;
      }
      pending.current = { ...pending.current, ...preferenceBody(patch) };
      if (options?.deferMs === undefined) {
        flush();
        return;
      }
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
      timer.current = window.setTimeout(flush, options.deferMs);
    },
    [store, signedIn, flush],
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
 * Persona and lore come from getCompanionPersona / updateCompanionPersona /
 * resetCompanionPersona and listCompanionLore / createCompanionLore /
 * updateCompanionLore / deleteCompanionLore / resetCompanionLore, always in
 * the current interface locale. Account-written fragments have `u-` ids;
 * every other fragment of a preset is authored lore.
 */
export const COMPANION_STORY_SUPPORTED = true;

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

type StoryLocale = "en" | "zh-TW" | "zh-CN";

const ACCOUNT_LORE_PREFIX = "u-";

function storyLocale(locale: string): StoryLocale {
  return locale === "zh-TW" || locale === "zh-CN" ? locale : "en";
}

/** Map one lore response to fragments; account rows start with `u-`. */
export function loreFragments(
  response: Pick<CompanionLoreSchema, "fragments">,
  ref: CompanionRef,
): readonly LoreFragment[] {
  const preset = ref.startsWith("preset:");
  return response.fragments
    .map((row) =>
      parseLoreFragment({
        ...row,
        is_default: preset && !row.id.startsWith(ACCOUNT_LORE_PREFIX),
      }),
    )
    .filter((item): item is LoreFragment => item !== null);
}

export function useCompanionStory(ref: CompanionRef): CompanionStory {
  const { locale: uiLocale } = useI18n();
  const locale = storyLocale(uiLocale);
  const queryClient = useQueryClient();
  const enabled = COMPANION_STORY_SUPPORTED && ref.length > 0;
  const params = useMemo(() => ({ locale }), [locale]);
  const personaQuery = useGetCompanionPersona(ref, params, { query: { enabled } });
  const loreQuery = useListCompanionLore(ref, params, { query: { enabled } });
  const persona = personaQuery.data;
  const lore = loreQuery.data;
  return useMemo(() => {
    const personaKey = getGetCompanionPersonaQueryKey(ref, params);
    const loreKey = getListCompanionLoreQueryKey(ref, params);
    const setLore = (next: CompanionLoreSchema) => {
      queryClient.setQueryData(loreKey, next);
    };
    return {
      supported: enabled,
      isLoading: personaQuery.isLoading || loreQuery.isLoading,
      isError: personaQuery.isError || loreQuery.isError,
      persona:
        persona === undefined ? null : { text: persona.persona, isDefault: persona.is_default },
      lore: lore === undefined ? [] : loreFragments(lore, ref),
      savePersona: async (text) => {
        queryClient.setQueryData(
          personaKey,
          await updateCompanionPersona(ref, { persona: text }, params),
        );
      },
      resetPersona: async () => {
        queryClient.setQueryData(personaKey, await resetCompanionPersona(ref, params));
      },
      createLore: async (input) => {
        setLore(
          await createCompanionLore(
            ref,
            { text: input.text, themes: [...input.themes], weight: tierToWeight(input.tier) },
            params,
          ),
        );
      },
      updateLore: async (id, input) => {
        setLore(
          await updateCompanionLore(
            ref,
            id,
            { text: input.text, themes: [...input.themes], weight: tierToWeight(input.tier) },
            params,
          ),
        );
      },
      deleteLore: async (id) => {
        setLore(await deleteCompanionLore(ref, id, params));
      },
      resetLore: async () => {
        setLore(await resetCompanionLore(ref, params));
      },
    };
  }, [
    enabled,
    lore,
    loreQuery.isError,
    loreQuery.isLoading,
    params,
    persona,
    personaQuery.isError,
    personaQuery.isLoading,
    queryClient,
    ref,
  ]);
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
