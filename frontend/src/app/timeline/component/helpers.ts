/** Date, URL, and formatting helpers for the timeline workspace. */

const DATE_INPUT = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})/;

/** The API accepts anchors from 1900 through 2200. */
export const MIN_YEAR = 1900;
export const MAX_YEAR = 2200;

/** Window lengths offered by the compact range control. */
export const RANGE_OPTIONS = [7, 14, 30, 90, 365] as const;
export const DEFAULT_RANGE = 30;

/** The demo seed writes events between August and September 2026. */
export const DEMO_SEASON_ANCHOR = new Date(2026, 8, 30);
export const DEMO_SEASON_RANGE = 90;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function readInteger(raw: string | null, min: number, max: number): number | null {
  if (raw === null || !/^\d+$/.test(raw)) {
    return null;
  }
  const value = Number(raw);
  return Number.isInteger(value) && value >= min && value <= max ? value : null;
}

/** Reads `year`, `month`, and `day` together; a partial or invalid date is ignored. */
export function parseDateParams(params: URLSearchParams): Date | null {
  const year = readInteger(params.get("year"), MIN_YEAR, MAX_YEAR);
  const month = readInteger(params.get("month"), 1, 12);
  const day = readInteger(params.get("day"), 1, 31);
  if (year === null || month === null || day === null) {
    return null;
  }
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

/**
 * Reads the window length from `day_range`, falling back to the legacy `range`
 * parameter and finally to 30 days.
 */
export function readRangeParam(params: URLSearchParams): number {
  const canonical = readInteger(params.get("day_range"), 1, 366);
  if (canonical !== null) {
    return canonical;
  }
  return readInteger(params.get("range"), 1, 366) ?? DEFAULT_RANGE;
}

export function readHistoryParam(params: URLSearchParams): boolean {
  return params.get("include_history") === "true";
}

export function writeDateParams(params: URLSearchParams, date: Date): void {
  params.set("year", String(date.getFullYear()));
  params.set("month", String(date.getMonth() + 1));
  params.set("day", String(date.getDate()));
}

/** Writes the canonical `day_range` key and drops the legacy `range` key. */
export function writeRangeParam(params: URLSearchParams, range: number): void {
  params.set("day_range", String(range));
  params.delete("range");
}

export function writeHistoryParam(params: URLSearchParams, includeHistory: boolean): void {
  if (includeHistory) {
    params.set("include_history", "true");
  } else {
    params.delete("include_history");
  }
}

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** Whole calendar days between two local dates, immune to DST hour shifts. */
export function differenceInCalendarDays(later: Date, earlier: Date): number {
  const laterUtc = Date.UTC(later.getFullYear(), later.getMonth(), later.getDate());
  const earlierUtc = Date.UTC(earlier.getFullYear(), earlier.getMonth(), earlier.getDate());
  return Math.round((laterUtc - earlierUtc) / 86_400_000);
}

export function toDateInput(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Parses a date input without accepting JavaScript's silent month rollovers. */
export function parseDateInput(value: string): Date | null {
  if (!DATE_INPUT.test(value)) {
    return null;
  }
  const [yearText, monthText, dayText] = value.split("-");
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  if (year < MIN_YEAR || year > MAX_YEAR) {
    return null;
  }
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

/** Parses the date portion of a backend timestamp without timezone drift. */
export function parseIsoDay(value: string): Date | null {
  const match = ISO_DAY.exec(value);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < 1 || year > 9999) {
    return null;
  }
  const date = new Date(0);
  date.setHours(0, 0, 0, 0);
  date.setFullYear(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return null;
  }
  return date;
}

export function isWithinApiRange(date: Date): boolean {
  return date.getFullYear() >= MIN_YEAR && date.getFullYear() <= MAX_YEAR;
}

function asValidDate(value: string | Date): Date | null {
  const date = typeof value === "string" ? parseIsoDay(value) : value;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

/** `YYYY.MM.DD`, used by the archive's folio-style metadata pills. */
export function formatDotDay(value: string | Date): string {
  const date = asValidDate(value);
  if (!date) {
    return typeof value === "string" ? value : "—";
  }
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}`;
}

export function formatDotRange(start: string, end: string): string {
  const startDay = start.slice(0, 10).replaceAll("-", ".");
  const endDay = end.slice(0, 10).replaceAll("-", ".");
  return `${startDay} \u2500 ${endDay}`;
}

const FULL_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const SHORT_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
});

function formatDayString(value: string, withYear: boolean): string {
  const date = parseIsoDay(value);
  if (!date) {
    return value.slice(0, 10);
  }
  return (withYear ? FULL_DATE : SHORT_DATE).format(date);
}

/** A compact, locale-stable range caption such as `01 Sep – 30 Sep 2026`. */
export function formatRangeCaption(start: string, end: string): string {
  const startDay = start.slice(0, 10);
  const endDay = end.slice(0, 10);
  if (startDay === endDay) {
    return formatDayString(endDay, true);
  }
  const startDate = parseIsoDay(startDay);
  const endDate = parseIsoDay(endDay);
  const sameYear =
    startDate !== null && endDate !== null && startDate.getFullYear() === endDate.getFullYear();
  return `${formatDayString(startDay, !sameYear)} \u2013 ${formatDayString(endDay, true)}`;
}

export function formatCalendarDay(value: string | Date): string {
  const date = asValidDate(value);
  return date ? FULL_DATE.format(date) : "—";
}

export function formatShortDay(value: string | Date): string {
  const date = asValidDate(value);
  return date ? SHORT_DATE.format(date) : "—";
}

/** Human-readable read error copy without leaking request internals. */
export function errorText(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return "The archive did not answer.";
}
