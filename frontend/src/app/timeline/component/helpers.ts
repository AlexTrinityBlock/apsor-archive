/** Date, URL, and error helpers shared by the timeline surfaces. */

const DATE_INPUT = /^\d{4}-\d{2}-\d{2}$/;

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
  const year = readInteger(params.get("year"), 1900, 2200);
  const month = readInteger(params.get("month"), 1, 12);
  const day = readInteger(params.get("day"), 1, 31);
  if (year === null || month === null || day === null) {
    return null;
  }
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

/** Reads the display window length, falling back to a single day. */
export function readRangeParam(params: URLSearchParams): number {
  return readInteger(params.get("range"), 1, 366) ?? 30;
}

export function readHistoryParam(params: URLSearchParams): boolean {
  return params.get("include_history") === "true";
}

export function writeDateParams(params: URLSearchParams, date: Date): void {
  params.set("year", String(date.getFullYear()));
  params.set("month", String(date.getMonth() + 1));
  params.set("day", String(date.getDate()));
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
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
  if (year < 1900 || year > 2200) {
    return null;
  }
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

export function formatRangeCaption(anchor: Date, range: number): string {
  const start = addDays(anchor, -(range - 1));
  const startLabel = start.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const endLabel = anchor.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  return range === 1 ? endLabel : `${startLabel} \u2013 ${endLabel}`;
}

export function formatDay(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function nowLocalInput(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** Human-readable mutation error copy without leaking request internals. */
export function errorText(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return "The archive did not answer.";
}
