/**
 * Pure layout and filter logic for root's companion views: the fragment
 * constellation, the bond timeline, fragment filters, and activity sparklines.
 * Kept free of React so `bun test` can cover it.
 */

export type FragmentWeight = "everyday" | "past" | "heart";
export type FragmentOrigin = "preset" | "admin" | "user" | "generated";
export type ToldFilter = "all" | "told" | "untold";

/**
 * A memory as the admin views see it. Nothing is locked: every memory is
 * visible to the librarian, who judges its weight herself. The API may send
 * the older `tier` (first, familiar, rare) or the newer `weight`; both map
 * onto the same three weights.
 */
export interface FragmentLike {
  readonly key: string;
  readonly tier?: string | null;
  readonly weight?: string | null;
  readonly state?: string | null;
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
  readonly weight: FragmentWeight;
  readonly told: boolean;
  readonly origin: FragmentOrigin;
  readonly hidden: boolean;
}

export const WEIGHT_ORDER: readonly FragmentWeight[] = [
  "everyday",
  "past",
  "heart",
];
const WEIGHT_RADIUS: Readonly<Record<FragmentWeight, number>> = {
  everyday: 0.36,
  past: 0.62,
  heart: 0.86,
};
const TIER_TO_WEIGHT: Readonly<Record<string, FragmentWeight>> = {
  first: "everyday",
  familiar: "past",
  rare: "heart",
  everyday: "everyday",
  past: "past",
  heart: "heart",
};
const WEIGHT_TO_TIER: Readonly<
  Record<FragmentWeight, "first" | "familiar" | "rare">
> = {
  everyday: "first",
  past: "familiar",
  heart: "rare",
};

/** The weight of a memory from either the `weight` or the legacy `tier` field. */
export function weightOf(
  fragment: Pick<FragmentLike, "tier" | "weight">,
): FragmentWeight {
  return (
    TIER_TO_WEIGHT[fragment.weight ?? ""] ??
    TIER_TO_WEIGHT[fragment.tier ?? ""] ??
    "everyday"
  );
}

/** Map a weight or a legacy tier value to a weight (unknown values: everyday). */
export function asWeight(value: string | null | undefined): FragmentWeight {
  return TIER_TO_WEIGHT[value ?? ""] ?? "everyday";
}

/** The legacy tier value the current API still accepts for a weight. */
export function tierForWeight(
  weight: FragmentWeight,
): "first" | "familiar" | "rare" {
  return WEIGHT_TO_TIER[weight];
}

/** Whether the librarian has already told this memory to the account. */
export function isTold(
  fragment: Pick<FragmentLike, "state" | "told_count">,
): boolean {
  return fragment.state === "told" || fragment.told_count > 0;
}

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
 * Place every memory on three concentric rings by weight (everyday inside,
 * the past, then what lies close to the heart). Positions depend only on the
 * keys, so a star never jumps between renders. Coordinates are in a 0..size
 * square centred on size/2. Told memories shine; untold ones glimmer.
 */
export function layoutStars(
  fragments: readonly FragmentLike[],
  size = 320,
): Star[] {
  const centre = size / 2;
  const stars: Star[] = [];
  for (const weight of WEIGHT_ORDER) {
    const ring = fragments.filter((fragment) => weightOf(fragment) === weight);
    ring.forEach((fragment, index) => {
      const jitter = hashUnit(fragment.key);
      const angle =
        ((index + jitter * 0.6) / Math.max(ring.length, 1)) * Math.PI * 2 +
        WEIGHT_ORDER.indexOf(weight) * 0.7;
      const radius = (WEIGHT_RADIUS[weight] + (jitter - 0.5) * 0.08) * centre;
      const told = isTold(fragment);
      stars.push({
        key: fragment.key,
        x: Math.round((centre + Math.cos(angle) * radius) * 10) / 10,
        y: Math.round((centre + Math.sin(angle) * radius) * 10) / 10,
        r: told ? 3.4 + Math.min(fragment.told_count, 4) * 0.5 : 2.6,
        weight,
        told,
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
  const lit = stars.filter((star) => star.told && !star.hidden);
  const lines: Array<readonly [Star, Star]> = [];
  for (let index = 1; index < lit.length; index += 1) {
    lines.push([lit[index - 1], lit[index]] as const);
  }
  return lines;
}

export interface FragmentFilter {
  readonly told: ToldFilter;
  readonly weight: FragmentWeight | "all";
  readonly origin: FragmentOrigin | "all";
  readonly query: string;
}

export const EMPTY_FILTER: FragmentFilter = {
  told: "all",
  weight: "all",
  origin: "all",
  query: "",
};

export function filterFragments<T extends FragmentLike>(
  fragments: readonly T[],
  filter: FragmentFilter,
): T[] {
  const query = filter.query.trim().toLowerCase();
  return fragments.filter((fragment) => {
    const told = isTold(fragment);
    return (
      (filter.told === "all" || (filter.told === "told") === told) &&
      (filter.weight === "all" || weightOf(fragment) === filter.weight) &&
      (filter.origin === "all" || fragment.origin === filter.origin) &&
      (!query ||
        fragment.key.toLowerCase().includes(query) ||
        fragment.text.toLowerCase().includes(query) ||
        fragment.themes.some((theme) => theme.toLowerCase().includes(query)))
    );
  });
}

export interface ToldCounts {
  readonly told: number;
  readonly untold: number;
  readonly total: number;
}

export function countTold(fragments: readonly FragmentLike[]): ToldCounts {
  let told = 0;
  let untold = 0;
  for (const fragment of fragments) {
    if (fragment.hidden_by_admin) continue;
    if (isTold(fragment)) told += 1;
    else untold += 1;
  }
  return { told, untold, total: told + untold };
}

export interface TimelineMark {
  readonly kind: "start" | "lastMoment" | "now" | "moment";
  readonly run: number;
  readonly at: number;
}

/**
 * Marks on the run axis: the first conversation, the last story moment, now,
 * and the next story moment. The span always leaves room for the next mark.
 */
export function timelineMarks(input: {
  readonly completedRuns: number;
  readonly lastStoryRun: number | null;
  readonly nextMomentIn: number | null;
}): { readonly span: number; readonly marks: TimelineMark[] } {
  const moment =
    input.nextMomentIn === null
      ? null
      : input.completedRuns + input.nextMomentIn;
  const span = Math.max(input.completedRuns, moment ?? 0, 1) * 1.08;
  const place = (run: number) => Math.min(1, Math.max(0, run / span));
  const marks: TimelineMark[] = [{ kind: "start", run: 0, at: 0 }];
  if (input.lastStoryRun !== null && input.lastStoryRun > 0) {
    marks.push({
      kind: "lastMoment",
      run: input.lastStoryRun,
      at: place(input.lastStoryRun),
    });
  }
  marks.push({
    kind: "now",
    run: input.completedRuns,
    at: place(input.completedRuns),
  });
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
