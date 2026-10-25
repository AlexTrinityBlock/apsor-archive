import type { Locale } from "./locales";

const DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "short",
  year: "numeric",
};

const DATE_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
};

const RELATIVE_UNITS: ReadonlyArray<
  readonly [Intl.RelativeTimeFormatUnit, number]
> = [
  ["year", 60 * 60 * 24 * 365],
  ["month", 60 * 60 * 24 * 30],
  ["week", 60 * 60 * 24 * 7],
  ["day", 60 * 60 * 24],
  ["hour", 60 * 60],
  ["minute", 60],
  ["second", 1],
];

function toDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Locale-aware formatters consumed by the provider and page components. */
export interface I18nFormatters {
  readonly formatDate: (value: string | Date) => string;
  readonly formatDateTime: (value: string | Date) => string;
  readonly formatNumber: (value: number) => string;
  readonly formatRelative: (value: string | Date) => string;
}

/** Builds `Intl` formatters once per locale change. */
export function createFormatters(locale: Locale): I18nFormatters {
  const date = new Intl.DateTimeFormat(locale, DATE_OPTIONS);
  const dateTime = new Intl.DateTimeFormat(locale, DATE_TIME_OPTIONS);
  const number = new Intl.NumberFormat(locale);
  const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  const formatRelative = (value: string | Date): string => {
    const parsed = toDate(value);
    if (!parsed) {
      return "—";
    }
    const deltaSeconds = Math.round((parsed.getTime() - Date.now()) / 1000);
    for (const [unit, seconds] of RELATIVE_UNITS) {
      if (Math.abs(deltaSeconds) >= seconds || unit === "second") {
        return relative.format(Math.round(deltaSeconds / seconds), unit);
      }
    }
    return relative.format(0, "second");
  };

  return {
    formatDate: (value) => {
      const parsed = toDate(value);
      return parsed ? date.format(parsed) : "—";
    },
    formatDateTime: (value) => {
      const parsed = toDate(value);
      return parsed ? dateTime.format(parsed) : "—";
    },
    formatNumber: (value) => number.format(value),
    formatRelative,
  };
}
