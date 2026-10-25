import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { readPageContextEntry } from "../page-context";

/**
 * A captured page snapshot in the transcript.
 *
 * This is deliberately not a user marginalium: the keeper did not write it,
 * and it is excluded from user-message counts. The full text is expandable
 * because the model receives it as a data envelope.
 */
export function PageContextCard({ entry }: { readonly entry: AgentEntrySchema }) {
  const { t, formatNumber } = useI18n();
  const context = readPageContextEntry(entry);
  if (!context) {
    return null;
  }

  return (
    <details className="pi-context-card">
      <summary className="pi-context-card__summary">
        <span className="pi-context-card__seal" aria-hidden="true">
          <Icon name="layers" size={14} />
        </span>
        <span className="pi-context-card__copy">
          <span className="pi-context-card__eyebrow">
            {t("chat.pageContext.eyebrow")}
            {context.truncated ? (
              <Badge tone="ochre">{t("chat.pageContext.trimmed")}</Badge>
            ) : null}
          </span>
          <span className="pi-context-card__title">
            {context.title ?? context.path}
          </span>
          <code className="pi-context-card__path">{context.path}</code>
        </span>
        <span className="pi-context-card__meta">
          {t("chat.pageContext.chars", {
            count: formatNumber(context.textChars),
          })}
          <Icon name="chevron-down" size={13} />
        </span>
      </summary>
      <div className="pi-context-card__body">
        <p className="pi-context-card__note">{t("chat.pageContext.note")}</p>
        {context.text.length > 0 ? (
          <pre className="pi-context-card__text">{context.text}</pre>
        ) : (
          <p className="pi-context-card__empty">
            {t("chat.pageContext.empty")}
          </p>
        )}
      </div>
    </details>
  );
}
