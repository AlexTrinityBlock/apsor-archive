/**
 * Companion story model: persona text, lore fragments, and lore surfaced in
 * search tool data. Lore is authored content: it is shown as written and
 * never translated, and it is never presented as archive evidence.
 */

export type LoreTier = "first" | "familiar" | "rare";

export const LORE_TIERS: readonly LoreTier[] = ["first", "familiar", "rare"];
export const PERSONA_MAX = 4000;
export const LORE_TEXT_MAX = 2000;
export const THEME_MAX_LENGTH = 32;
export const THEMES_MAX = 8;

export interface CompanionPersona {
  readonly text: string;
  readonly isDefault: boolean;
}

export interface LoreFragment {
  readonly id: string;
  readonly tier: LoreTier;
  readonly text: string;
  readonly themes: readonly string[];
  readonly isDefault: boolean;
  readonly edited: boolean;
}

export interface LoreInput {
  readonly text: string;
  readonly themes: readonly string[];
  readonly tier: LoreTier;
}

type JsonObject = Readonly<Record<string, unknown>>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readId(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return typeof value === "string" && value.length > 0 && value.length <= 80 ? value : null;
}

export function isLoreTier(value: unknown): value is LoreTier {
  return value === "first" || value === "familiar" || value === "rare";
}

/** The API's memory weight (everyday, past, heart) for an editor tier. */
export type LoreWeight = "everyday" | "past" | "heart";

const TIER_WEIGHTS: Readonly<Record<LoreTier, LoreWeight>> = {
  first: "everyday",
  familiar: "past",
  rare: "heart",
};

export function tierToWeight(tier: LoreTier): LoreWeight {
  return TIER_WEIGHTS[tier];
}

/** Read a row's weight (or a legacy tier) as an editor tier. */
export function readLoreTier(value: unknown): LoreTier | null {
  if (isLoreTier(value)) {
    return value;
  }
  const match = (Object.keys(TIER_WEIGHTS) as LoreTier[]).find(
    (tier) => TIER_WEIGHTS[tier] === value,
  );
  return match ?? null;
}

/** Parse one lore fragment from an API row; unknown shapes are dropped. */
export function parseLoreFragment(value: unknown): LoreFragment | null {
  if (!isObject(value)) {
    return null;
  }
  const id = readId(value.id);
  if (id === null || typeof value.text !== "string") {
    return null;
  }
  const themes = Array.isArray(value.themes)
    ? value.themes.filter((theme): theme is string => typeof theme === "string").slice(0, THEMES_MAX)
    : [];
  return {
    id,
    tier: readLoreTier(value.weight) ?? readLoreTier(value.tier) ?? "familiar",
    text: value.text,
    themes,
    isDefault: value.is_default === true || value.isDefault === true,
    edited: value.edited === true,
  };
}

export interface LoreTierGroup {
  readonly tier: LoreTier;
  readonly fragments: readonly LoreFragment[];
}

/** Fragments grouped in tier order; empty tiers are omitted. */
export function groupLoreByTier(fragments: readonly LoreFragment[]): readonly LoreTierGroup[] {
  return LORE_TIERS.map((tier) => ({
    tier,
    fragments: fragments.filter((fragment) => fragment.tier === tier),
  })).filter((group) => group.fragments.length > 0);
}

/** Trim, collapse spaces, and bound a theme chip; empty results are null. */
export function normalizeTheme(value: string): string | null {
  const theme = value.trim().replace(/\s+/g, " ").slice(0, THEME_MAX_LENGTH);
  return theme.length > 0 ? theme : null;
}

export function addTheme(themes: readonly string[], value: string): readonly string[] {
  const theme = normalizeTheme(value);
  if (theme === null || themes.length >= THEMES_MAX) {
    return themes;
  }
  const exists = themes.some((item) => item.toLowerCase() === theme.toLowerCase());
  return exists ? themes : [...themes, theme];
}

export type LoreProblem = "empty" | "tooLong";

export function validateLore(input: LoreInput): LoreProblem | null {
  const text = input.text.trim();
  if (text.length === 0) {
    return "empty";
  }
  return text.length > LORE_TEXT_MAX ? "tooLong" : null;
}

export interface SurfacedLore {
  readonly id: string;
  readonly text: string;
}

/** Lore the search tool surfaced alongside archive evidence (`data.lore`). */
export function readSurfacedLore(data: unknown): readonly SurfacedLore[] {
  if (!isObject(data) || !Array.isArray(data.lore)) {
    return [];
  }
  const items: SurfacedLore[] = [];
  for (const raw of data.lore) {
    if (!isObject(raw) || typeof raw.text !== "string") {
      continue;
    }
    const id = readId(raw.id);
    const text = raw.text.trim();
    if (id !== null && text.length > 0) {
      items.push({ id, text });
    }
    if (items.length >= 3) {
      break;
    }
  }
  return items;
}

/** A short, word-boundary snippet for a collapsed fragment. */
export function loreSnippet(text: string, max = 160): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) {
    return clean;
  }
  const cut = clean.slice(0, max);
  const space = cut.lastIndexOf(" ");
  let head = space > max * 0.6 ? cut.slice(0, space) : cut;
  while (head.length > 0 && " ,.;:".includes(head.charAt(head.length - 1))) {
    head = head.slice(0, -1);
  }
  return `${head}…`;
}
