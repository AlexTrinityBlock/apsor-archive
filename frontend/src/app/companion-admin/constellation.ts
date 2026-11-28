/**
 * Pure layout and filter logic for root's companion views: the fragment
 * constellation, the bond timeline, fragment filters, and activity sparklines.
 * Kept free of React so `bun test` can cover it.
 */

export type FragmentState = "locked" | "unlocked" | "told";
export type FragmentTier = "first" | "familiar" | "rare";
export type FragmentOrigin = "preset" | "admin" | "user" | "generated";

export interface FragmentLike {
  readonly key: string;
  readonly tier: FragmentTier;
  readonly state: FragmentState;
  readonly origin: FragmentOrigin;
  readonly text: string;
  readonly themes: readonly string[];
  readonly told_count: number;
  readonly hidden_by_admin?: boolean;
}

export interface Star {
  readonly key: string;
  readonly x: number;
  readonly y: number;
  readonly r: number;
  readonly tier: FragmentTier;
  readonly state: FragmentState;
  readonly origin: FragmentOrigin;
  readonly hidden: boolean;
}

export const TIER_ORDER: readonly FragmentTier[] = [
  "first",
  "familiar",
  "rare",
];
const TIER_RADIUS: Readonly<Record<FragmentTier, number>> = {
  first: 0.36,
  familiar: 0.62,
  rare: 0.86,
};

/** A stable 0..1 pseudo-random number for a string (FNV-1a). */
export function hashUnit(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0) / 0xffffffff;
}

/**
 * Place fragments on three concentric rings (first, familiar, rare). Positions
 * depend only on the fragment keys, so a star never jumps between renders.
 * Coordinates are in a 0..size square centred on size/2.
 */
export function layoutStars(
  fragments: readonly FragmentLike[],
  size = 320,
): Star[] {
  const centre = size / 2;
  const stars: Star[] = [];
  for (const tier of TIER_ORDER) {
    const ring = fragments.filter((fragment) => fragment.tier === tier);
    ring.forEach((fragment, index) => {
      const jitter = hashUnit(fragment.key);
      const angle =
        ((index + jitter * 0.6) / Math.max(ring.length, 1)) * Math.PI * 2 +
        TIER_ORDER.indexOf(tier) * 0.7;
      const radius = (TIER_RADIUS[tier] + (jitter - 0.5) * 0.08) * centre;
      stars.push({
        key: fragment.key,
        x: Math.round((centre + Math.cos(angle) * radius) * 10) / 10,
        y: Math.round((centre + Math.sin(angle) * radius) * 10) / 10,
        r:
          fragment.state === "told"
            ? 3.4 + Math.min(fragment.told_count, 4) * 0.5
            : 2.4,
        tier,
        state: fragment.state,
        origin: fragment.origin,
        hidden: fragment.hidden_by_admin === true,
      });
    });
  }
  return stars;
}

/** Faint lines joining told stars in the order of their ring and position. */
export function constellationLines(
  stars: readonly Star[],
): Array<readonly [Star, Star]> {
  const lit = stars.filter((star) => star.state === "told" && !star.hidden);
  const lines: Array<readonly [Star, Star]> = [];
  for (let index = 1; index < lit.length; index += 1) {
    lines.push([lit[index - 1], lit[index]] as const);
  }
  return lines;
}

export interface FragmentFilter {
  readonly state: FragmentState | "all";
  readonly tier: FragmentTier | "all";
  readonly origin: FragmentOrigin | "all";
  readonly query: string;
}

export const EMPTY_FILTER: FragmentFilter = {
  state: "all",
  tier: "all",
  origin: "all",
  query: "",
};

export function filterFragments<T extends FragmentLike>(
  fragments: readonly T[],
  filter: FragmentFilter,
): T[] {
  const query = filter.query.trim().toLowerCase();
  return fragments.filter(
    (fragment) =>
      (filter.state === "all" || fragment.state === filter.state) &&
      (filter.tier === "all" || fragment.tier === filter.tier) &&
      (filter.origin === "all" || fragment.origin === filter.origin) &&
      (!query ||
        fragment.key.toLowerCase().includes(query) ||
        fragment.text.toLowerCase().includes(query) ||
        fragment.themes.some((theme) => theme.toLowerCase().includes(query))),
  );
}

export interface StateCounts {
  readonly told: number;
  readonly unlocked: number;
  readonly locked: number;
  readonly total: number;
}

export function countStates(fragments: readonly FragmentLike[]): StateCounts {
  let told = 0;
  let unlocked = 0;
  let locked = 0;
  for (const fragment of fragments) {
    if (fragment.hidden_by_admin) {
      continue;
    }
    if (fragment.state === "told") told += 1;
    else if (fragment.state === "unlocked") unlocked += 1;
    else locked += 1;
  }
  return { told, unlocked, locked, total: told + unlocked + locked };
}

export interface TimelineMark {
  readonly kind: "familiar" | "rare" | "now" | "moment";
  readonly run: number;
  readonly at: number;
}

/**
 * Marks on a run axis from 0 to a span that always shows the next milestone:
 * tier unlocks, the current run count, and the next story moment.
 */
export function timelineMarks(input: {
  readonly completedRuns: number;
  readonly familiarRuns: number;
  readonly rareRuns: number;
  readonly nextMomentIn: number | null;
}): { readonly span: number; readonly marks: TimelineMark[] } {
  const moment =
    input.nextMomentIn === null
      ? null
      : input.completedRuns + input.nextMomentIn;
  const span =
    Math.max(input.rareRuns, input.completedRuns, moment ?? 0, 1) * 1.08;
  const place = (run: number) => Math.min(1, Math.max(0, run / span));
  const marks: TimelineMark[] = [
    {
      kind: "familiar",
      run: input.familiarRuns,
      at: place(input.familiarRuns),
    },
    { kind: "rare", run: input.rareRuns, at: place(input.rareRuns) },
    { kind: "now", run: input.completedRuns, at: place(input.completedRuns) },
  ];
  if (moment !== null) {
    marks.push({ kind: "moment", run: moment, at: place(moment) });
  }
  return { span, marks };
}

/** An SVG polyline `points` string for a small sparkline. */
export function sparklinePoints(
  values: readonly number[],
  width = 72,
  height = 18,
): string {
  if (values.length === 0) {
    return "";
  }
  const peak = Math.max(...values, 1);
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  return values
    .map((value, index) => {
      const x = Math.round(index * step * 10) / 10;
      const y =
        Math.round((height - 1 - (value / peak) * (height - 2)) * 10) / 10;
      return `${x},${y}`;
    })
    .join(" ");
}

export type DirectoryFilter =
  "all" | "root" | "active" | "disabled" | "companion";

export interface DirectoryRow {
  readonly username: string;
  readonly display_name?: string | null;
  readonly role: string;
  readonly is_active: boolean;
}

export function matchesDirectory(
  row: DirectoryRow,
  query: string,
  filter: DirectoryFilter,
  companionActive: boolean,
): boolean {
  const needle = query.trim().toLowerCase();
  if (
    needle &&
    !row.username.toLowerCase().includes(needle) &&
    !(row.display_name ?? "").toLowerCase().includes(needle)
  ) {
    return false;
  }
  switch (filter) {
    case "root":
      return row.role === "root";
    case "active":
      return row.is_active;
    case "disabled":
      return !row.is_active;
    case "companion":
      return companionActive;
    default:
      return true;
  }
}

/** Placeholders like `{name}` in a template body, in first-use order. */
export function templatePlaceholders(body: string): string[] {
  const seen: string[] = [];
  for (const match of body.matchAll(/\{([a-z_]+)\}/g)) {
    if (!seen.includes(match[1])) {
      seen.push(match[1]);
    }
  }
  return seen;
}

/** Minimal line diff (longest common subsequence) for revision comparison. */
export function lineDiff(
  before: string,
  after: string,
): Array<{ readonly kind: "same" | "add" | "remove"; readonly text: string }> {
  const a = before.split("\n");
  const b = after.split("\n");
  if (a.length * b.length > 400_000) {
    return [
      ...a.map((text) => ({ kind: "remove" as const, text })),
      ...b.map((text) => ({ kind: "add" as const, text })),
    ];
  }
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const out: Array<{ kind: "same" | "add" | "remove"; text: string }> = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      out.push({ kind: "remove", text: a[i] });
      i += 1;
    } else {
      out.push({ kind: "add", text: b[j] });
      j += 1;
    }
  }
  while (i < a.length) out.push({ kind: "remove", text: a[i++] });
  while (j < b.length) out.push({ kind: "add", text: b[j++] });
  return out;
}
