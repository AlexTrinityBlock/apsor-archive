import { Icon } from "../../../component/Icon";
import { formatArgumentValue } from "../../../chat/format";
import { useI18n, type TranslationKey } from "../../../i18n";
import { textField } from "../../trace";
import type { PanelProps } from "./common";

const SUGGESTION_KEYS: Readonly<Record<string, TranslationKey>> = {
  invalid_tool_arguments: "chat.panels.error.suggestionInvalidArguments",
  memory_confirmation_required: "chat.panels.error.suggestionConfirmation",
  tool_unavailable: "chat.panels.error.suggestionUnavailable",
  tool_execution_failed: "chat.panels.error.suggestionExecution",
  file_not_found: "chat.panels.error.suggestionFileMissing",
  memory_not_found: "chat.panels.error.suggestionMemoryMissing",
  invalid_chunk_window: "chat.panels.error.suggestionChunkWindow",
};

function suggestionFor(code: string | null, t: (key: TranslationKey) => string): string {
  if (!code) {
    return t("chat.panels.error.suggestionNoCode");
  }
  return (
    SUGGESTION_KEYS[code]
      ? t(SUGGESTION_KEYS[code])
      : t("chat.panels.error.suggestionGeneric")
  );
}

/** A repair bench for any failed or unstructured tool result. */
export function ToolErrorPanel({ item }: PanelProps) {
  const { t } = useI18n();
  const code = item.errorCode ?? textField(item.data, "code");
  const detail =
    item.detail ??
    textField(item.data, "detail") ??
    textField(item.data, "message") ??
    t("chat.panels.error.detailFallback");
  const argumentEntries = item.arguments ? Object.entries(item.arguments) : [];

  return (
    <div className="pi-repair">
      <div className="pi-repair__lamp" aria-hidden="true">
        <span />
      </div>
      <header className="pi-repair__head">
        <span className="pi-repair__mark" aria-hidden="true">
          <Icon name="info" size={18} />
        </span>
        <div>
          <p className="eyebrow">{t("chat.panels.error.eyebrow")}</p>
          <strong>{code ?? "unstructured_error"}</strong>
        </div>
      </header>

      <p className="pi-repair__detail">{detail}</p>

      <section className="pi-repair__section">
        <p className="eyebrow">{t("chat.panels.error.nextStep")}</p>
        <p>{suggestionFor(code, t)}</p>
      </section>

      {argumentEntries.length > 0 ? (
        <section className="pi-repair__section">
          <p className="eyebrow">{t("chat.panels.error.argumentsReceived")}</p>
          <dl className="pi-repair__args">
            {argumentEntries.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{formatArgumentValue(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <p className="pi-repair__note">{t("chat.panels.error.note")}</p>
    </div>
  );
}
