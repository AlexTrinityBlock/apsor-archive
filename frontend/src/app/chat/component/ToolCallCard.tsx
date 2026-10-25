import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { truncate } from "../../../lib/format";
import { formatArgumentValue } from "../format";
import type { ToolCallMeta, ToolResultMeta } from "../types";
import { toolStatusLabel } from "./status";

interface ToolCallCardProps {
  readonly call: ToolCallMeta;
  readonly result: ToolResultMeta | null;
  readonly index: number;
  readonly selected?: boolean;
  readonly onSelect?: (callId: string) => void;
}

function argumentSummary(call: ToolCallMeta, noArguments: string): string {
  if (call.arguments) {
    const first = Object.entries(call.arguments)[0];
    if (first) {
      return `${first[0]}: ${formatArgumentValue(first[1])}`;
    }
  }
  if (call.rawArguments) {
    return truncate(call.rawArguments, 90);
  }
  return noArguments;
}

function formatDuration(value: number | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)} s`;
  }
  return `${value} ms`;
}

/** A compact tool step. Selecting it pins the matching inspector trace item. */
export function ToolCallCard({
  call,
  result,
  index,
  selected = false,
  onSelect,
}: ToolCallCardProps) {
  const { t } = useI18n();
  const status = result?.status ?? null;
  const statusLabel = toolStatusLabel(
    status,
    t,
    result ? t("chat.common.recorded") : t("chat.tool.awaitingResult"),
  );
  const duration = formatDuration(result?.durationMs);
  const isError = status?.toLowerCase() === "error";

  const className = [
    "tool-step-chip",
    selected ? "is-active" : null,
    isError ? "is-error" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type="button"
      className={className}
      onClick={onSelect ? () => onSelect(call.id) : undefined}
      aria-pressed={onSelect ? selected : undefined}
      title={onSelect ? t("chat.tool.inspect") : undefined}
    >
      <span className="tool-step-chip__left">
        <span className="tool-step-chip__index" aria-hidden="true">
          {String(index + 1).padStart(2, "0")}
        </span>
        <Icon name="spark" size={12} />
        <code className="tool-step-chip__name">{call.name}</code>
        <span className="tool-step-chip__args">
          {argumentSummary(call, t("chat.tool.noArguments"))}
        </span>
      </span>
      <span className="tool-step-chip__right">
        {duration ? <span>{duration}</span> : null}
        <span
          className={
            isError
              ? "tool-step-chip__status is-error"
              : "tool-step-chip__status"
          }
        >
          {statusLabel}
        </span>
      </span>
    </button>
  );
}
