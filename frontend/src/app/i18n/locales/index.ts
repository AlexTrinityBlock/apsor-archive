import { core as enCore } from "./en/core";
import { chat as enChat } from "./en/chat";
import { library as enLibrary } from "./en/library";
import { memory as enMemory } from "./en/memory";
import { insights as enInsights } from "./en/insights";
import { settings as enSettings } from "./en/settings";
import { systemPrompt as enSystemPrompt } from "./en/systemPrompt";

import { core as zhTwCore } from "./zh-TW/core";
import { chat as zhTwChat } from "./zh-TW/chat";
import { library as zhTwLibrary } from "./zh-TW/library";
import { memory as zhTwMemory } from "./zh-TW/memory";
import { insights as zhTwInsights } from "./zh-TW/insights";
import { settings as zhTwSettings } from "./zh-TW/settings";
import { systemPrompt as zhTwSystemPrompt } from "./zh-TW/systemPrompt";

import { core as zhCnCore } from "./zh-CN/core";
import { chat as zhCnChat } from "./zh-CN/chat";
import { library as zhCnLibrary } from "./zh-CN/library";
import { memory as zhCnMemory } from "./zh-CN/memory";
import { insights as zhCnInsights } from "./zh-CN/insights";
import { settings as zhCnSettings } from "./zh-CN/settings";
import { systemPrompt as zhCnSystemPrompt } from "./zh-CN/systemPrompt";

/** The locales the archive interface can render. */
export const LOCALES = ["en", "zh-TW", "zh-CN"] as const;

/** A supported interface locale. */
export type Locale = (typeof LOCALES)[number];

/**
 * The English dictionary is the source of truth. Each namespace is a nested
 * object; translations use dot-path keys such as `core.home.title`.
 */
export interface TranslationDictionary {
  readonly core: typeof enCore;
  readonly chat: typeof enChat;
  readonly library: typeof enLibrary;
  readonly memory: typeof enMemory;
  readonly insights: typeof enInsights;
  readonly settings: typeof enSettings;
  readonly systemPrompt: typeof enSystemPrompt;
}

/** Namespaces are separate files so surface agents can fill them independently. */
export type Namespace = keyof TranslationDictionary;

/** Namespace list in the same order as the settings/UI surfaces. */
export const NAMESPACES = [
  "core",
  "chat",
  "library",
  "memory",
  "insights",
  "settings",
  "systemPrompt",
] as const satisfies readonly Namespace[];

/**
 * Every locale dictionary, keyed by locale. Parity is enforced by
 * `bun run i18n:check` rather than the type system so surface agents can fill
 * one language at a time without blocking another agent's typecheck.
 */
export const dictionaries = {
  en: {
    core: enCore,
    chat: enChat,
    library: enLibrary,
    memory: enMemory,
    insights: enInsights,
    settings: enSettings,
    systemPrompt: enSystemPrompt,
  },
  "zh-TW": {
    core: zhTwCore,
    chat: zhTwChat,
    library: zhTwLibrary,
    memory: zhTwMemory,
    insights: zhTwInsights,
    settings: zhTwSettings,
    systemPrompt: zhTwSystemPrompt,
  },
  "zh-CN": {
    core: zhCnCore,
    chat: zhCnChat,
    library: zhCnLibrary,
    memory: zhCnMemory,
    insights: zhCnInsights,
    settings: zhCnSettings,
    systemPrompt: zhCnSystemPrompt,
  },
} satisfies Record<Locale, Record<Namespace, unknown>>;

type DotPaths<T> = T extends string
  ? never
  : {
      [K in keyof T & string]: T[K] extends string
        ? K
        : `${K}.${DotPaths<T[K]>}`;
    }[keyof T & string];

/** Every translatable key, derived from the English source of truth. */
export type TranslationKey = DotPaths<TranslationDictionary>;

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Flattens a nested dictionary into sorted dot-path string keys. */
export function flattenDictionaryKeys(value: unknown, prefix = ""): string[] {
  if (!isRecord(value)) {
    return [];
  }
  const keys: string[] = [];
  for (const [key, child] of Object.entries(value)) {
    const path = prefix.length > 0 ? `${prefix}.${key}` : key;
    if (typeof child === "string") {
      keys.push(path);
    } else if (isRecord(child)) {
      keys.push(...flattenDictionaryKeys(child, path));
    }
  }
  return keys.sort();
}

/** Returns the flattened keys for one namespace and locale. */
export function getNamespaceKeys(locale: Locale, namespace: Namespace): string[] {
  return flattenDictionaryKeys(dictionaries[locale][namespace]);
}

/** Total translatable string count for a locale. */
export function getLocaleKeyCount(locale: Locale): number {
  return NAMESPACES.reduce(
    (total, namespace) => total + getNamespaceKeys(locale, namespace).length,
    0,
  );
}

/** Missing and extra keys for one locale, relative to English. */
export interface LocaleKeyDiff {
  readonly missing: readonly string[];
  readonly extra: readonly string[];
}

/** Compares one locale against English, namespace by namespace. */
export function compareLocaleKeys(locale: Locale): Record<Namespace, LocaleKeyDiff> {
  const report: Partial<Record<Namespace, LocaleKeyDiff>> = {};
  for (const namespace of NAMESPACES) {
    const reference = new Set(getNamespaceKeys("en", namespace));
    const candidate = new Set(getNamespaceKeys(locale, namespace));
    report[namespace] = {
      missing: [...reference].filter((key) => !candidate.has(key)),
      extra: [...candidate].filter((key) => !reference.has(key)),
    };
  }
  return report as Record<Namespace, LocaleKeyDiff>;
}
