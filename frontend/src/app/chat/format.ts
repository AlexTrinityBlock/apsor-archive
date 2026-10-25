import { truncate } from "../../lib/format";

/** Compact, safe text for one structured tool argument value. */
export function formatArgumentValue(value: unknown): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return truncate(value, 160);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return truncate(
      value
        .map((item) =>
          typeof item === "string" ? item : JSON.stringify(item) ?? String(item),
        )
        .join(", "),
      160,
    );
  }
  const serialized = JSON.stringify(value);
  return serialized ? truncate(serialized, 160) : String(value);
}

/** A concise conversation title from the first user message. */
export function titleFromMessage(content: string): string {
  return truncate(content, 64);
}
