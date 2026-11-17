import { useI18n } from "../../i18n";
import { toolStatusLabel } from "./status";

export interface ToolDiagnosticItem {
  readonly id: string;
  readonly name: string;
  readonly status: string | null;
  readonly errorCode: string | null;
  readonly detail?: string | null;
}

/**
 * A collapsed record of failed tool calls.
 *
 * Failures are diagnostics, not the assistant's answer. Keeping them behind a
 * closed disclosure leaves the prose primary while the recorded error code and
 * detail stay available to a reader who asks for them.
 */
export function ToolDiagnostics({
  items,
}: {
  readonly items: readonly ToolDiagnosticItem[];
}) {
  const { t } = useI18n();
  if (items.length === 0) {
    return null;
  }
  return (
    <details className="chat-diagnostics">
      <summary>
        {t("chat.tool.diagnostics", { count: items.length })}
      </summary>
      <ul className="chat-diagnostics__list">
        {items.map((item) => (
          <li key={item.id}>
            <code>{item.name}</code>
            <span className="chat-diagnostics__status">
              {item.errorCode ??
                toolStatusLabel(item.status, t, t("chat.common.recorded"))}
            </span>
            {item.detail ? (
              <p className="chat-diagnostics__detail">{item.detail}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
