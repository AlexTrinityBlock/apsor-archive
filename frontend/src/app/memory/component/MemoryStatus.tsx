import type { MemorySchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";

interface MemoryStatusProps {
  readonly status: MemorySchema["status"];
  readonly small?: boolean;
}

/** Editorial status pill shared by vault cards and reader lineage. */
export function MemoryStatus({ status, small = false }: MemoryStatusProps) {
  const { t } = useI18n();

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
      {status === "active"
        ? t("memory.status.active")
        : t("memory.status.deprecated")}
    </span>
  );
}
