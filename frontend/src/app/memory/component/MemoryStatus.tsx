import type { MemorySchema } from "../../generated-apis-types/schemas";

interface MemoryStatusProps {
  readonly status: MemorySchema["status"];
  readonly small?: boolean;
}

/** Editorial status pill shared by vault cards and reader lineage. */
export function MemoryStatus({ status, small = false }: MemoryStatusProps) {
  return (
    <span
      className={[
        "memory-status",
        `memory-status--${status}`,
        small ? "memory-status--sm" : null,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span aria-hidden="true">●</span>
      {status === "active" ? "Active tip" : "Deprecated"}
    </span>
  );
}
