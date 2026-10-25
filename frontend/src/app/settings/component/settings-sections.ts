import type { TranslationKey } from "../../i18n";

/**
 * Settings sections in display order. The id doubles as the URL hash and as the
 * active tabpanel id, so the old `/settings#settings-*` deep links keep
 * resolving to the same tab.
 */
export const SETTINGS_SECTIONS = [
  {
    id: "settings-system-prompt",
    labelKey: "core.settingsNav.systemPrompt",
    index: "01",
  },
  {
    id: "settings-frequent-prompts",
    labelKey: "core.settingsNav.frequentPrompts",
    index: "02",
  },
  {
    id: "settings-providers",
    labelKey: "core.settingsNav.providers",
    index: "03",
  },
  {
    id: "settings-diagnostics",
    labelKey: "core.settingsNav.diagnostics",
    index: "04",
  },
  {
    id: "settings-agent-runtime",
    labelKey: "core.settingsNav.agentRuntime",
    index: "05",
  },
  {
    id: "settings-ingest-runtime",
    labelKey: "core.settingsNav.ingestRuntime",
    index: "06",
  },
  {
    id: "settings-maintenance",
    labelKey: "core.settingsNav.maintenance",
    index: "07",
  },
  {
    id: "settings-language",
    labelKey: "core.settingsNav.language",
    index: "08",
  },
] as const satisfies readonly {
  readonly id: string;
  readonly labelKey: TranslationKey;
  readonly index: string;
}[];

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]["id"];

export const DEFAULT_SETTINGS_SECTION: SettingsSectionId =
  SETTINGS_SECTIONS[0].id;

const SETTINGS_SECTION_IDS: ReadonlySet<string> = new Set(
  SETTINGS_SECTIONS.map((section) => section.id),
);

/** Stable tab button id shared by the tab strip and each tabpanel label. */
export function settingsTabId(section: SettingsSectionId): string {
  return `settings-tab-${section}`;
}

/**
 * Resolve a URL hash to a settings section. Empty or unrecognised hashes return
 * null so callers can distinguish "leave the current tab alone" from a real
 * section change.
 */
export function settingsSectionFromHash(
  hash: string,
): SettingsSectionId | null {
  const id = hash.replace(/^#/, "");
  return SETTINGS_SECTION_IDS.has(id) ? (id as SettingsSectionId) : null;
}

/** Resolve a URL hash to a section, falling back to the first tab. */
export function parseSettingsSectionHash(hash: string): SettingsSectionId {
  return settingsSectionFromHash(hash) ?? DEFAULT_SETTINGS_SECTION;
}
