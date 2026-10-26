import type { TranslationKey } from "../../i18n";

export type SettingsSectionRole = "all" | "root";

interface SettingsSectionDefinition {
  readonly id: string;
  readonly labelKey: TranslationKey;
  readonly roles: SettingsSectionRole;
}

/**
 * Settings sections in display order. The id doubles as the URL hash and as the
 * active tabpanel id, so the old `/settings#settings-*` deep links keep
 * resolving to the same tab. `roles` decides whether a tab is visible to every
 * account or only to the root account.
 */
export const SETTINGS_SECTIONS = [
  {
    id: "settings-system-prompt",
    labelKey: "core.settingsNav.systemPrompt",
    roles: "root",
  },
  {
    id: "settings-frequent-prompts",
    labelKey: "core.settingsNav.frequentPrompts",
    roles: "all",
  },
  {
    id: "settings-providers",
    labelKey: "core.settingsNav.providers",
    roles: "root",
  },
  {
    id: "settings-diagnostics",
    labelKey: "core.settingsNav.diagnostics",
    roles: "root",
  },
  {
    id: "settings-agent-runtime",
    labelKey: "core.settingsNav.agentRuntime",
    roles: "root",
  },
  {
    id: "settings-ingest-runtime",
    labelKey: "core.settingsNav.ingestRuntime",
    roles: "root",
  },
  {
    id: "settings-maintenance",
    labelKey: "core.settingsNav.maintenance",
    roles: "root",
  },
  {
    id: "settings-language",
    labelKey: "core.settingsNav.language",
    roles: "all",
  },
] as const satisfies readonly SettingsSectionDefinition[];

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]["id"];

/** A section as actually rendered, with a gap-free visible index. */
export interface SettingsSection {
  readonly id: SettingsSectionId;
  readonly labelKey: TranslationKey;
  readonly index: string;
}

/**
 * Select the sections visible to the account. Filtering happens before
 * numbering so a non-root tab strip starts at 01 and has no holes where
 * root-only tabs were removed.
 */
export function selectSettingsSections(
  isRoot: boolean,
): readonly SettingsSection[] {
  const visible: SettingsSection[] = [];
  for (const section of SETTINGS_SECTIONS) {
    if (section.roles === "root" && !isRoot) {
      continue;
    }
    visible.push({
      id: section.id,
      labelKey: section.labelKey,
      index: String(visible.length + 1).padStart(2, "0"),
    });
  }
  return visible;
}

const SETTINGS_SECTION_IDS: ReadonlySet<string> = new Set(
  SETTINGS_SECTIONS.map((section) => section.id),
);

export function isSettingsSectionVisible(
  section: SettingsSectionId,
  isRoot: boolean,
): boolean {
  const definition = SETTINGS_SECTIONS.find((item) => item.id === section);
  return definition !== undefined && (definition.roles === "all" || isRoot);
}

/** The first visible section is the fallback for empty or hidden deep links. */
export function defaultSettingsSection(isRoot: boolean): SettingsSectionId {
  return selectSettingsSections(isRoot)[0].id;
}

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

/**
 * Resolve a URL hash for initial mount and explicit section links. Unknown
 * hashes fall back to the first visible section, and a hidden root-only section
 * falls back the same way for a non-root reader.
 */
export function parseSettingsSectionHash(
  hash: string,
  isRoot: boolean,
): SettingsSectionId {
  const section = settingsSectionFromHash(hash);
  if (section !== null && isSettingsSectionVisible(section, isRoot)) {
    return section;
  }
  return defaultSettingsSection(isRoot);
}
