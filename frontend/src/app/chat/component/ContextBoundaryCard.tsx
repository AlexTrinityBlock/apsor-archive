import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n, type Translate } from "../../i18n";
import { isRecord, numberValue, stringValue, userText } from "../types";

function unescapeXmlText(value: string): string {
  return value
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

function tagText(content: string, tag: string): string | null {
  const open = `<${tag}>`;
  const close = `</${tag}>`;
  const start = content.indexOf(open);
  if (start < 0) {
    return null;
  }
  const from = start + open.length;
  const end = content.indexOf(close, from);
  if (end < 0) {
    return null;
  }
  const text = unescapeXmlText(content.slice(from, end)).trim();
  return text.length > 0 ? text : null;
}

function compactionContent(entry: AgentEntrySchema): {
  readonly lastUserInput: string | null;
  readonly summary: string | null;
} {
  const content = userText(entry);
  return {
    lastUserInput: tagText(content, "last_user_input"),
    summary: tagText(content, "summary"),
  };
}

function reasonLabel(reason: string | null, t: Translate): string | null {
  if (!reason) {
    return null;
  }
  if (reason === "manual") {
    return t("chat.boundary.manualCompaction");
  }
  if (reason === "auto_context_threshold") {
    return t("chat.boundary.threshold");
  }
  if (reason === "manual_clear") {
    return t("chat.boundary.manualClear");
  }
  return reason.replaceAll("_", " ");
}

function CompactionCard({ entry }: { readonly entry: AgentEntrySchema }) {
  const { t, formatNumber } = useI18n();
  const data = isRecord(entry.data) ? entry.data : {};
  const auto = data.auto === true;
  const reason = reasonLabel(stringValue(data.reason), t);
  const summaryChars = numberValue(data.summary_chars);
  const sourceCount = Array.isArray(data.source_entry_ids)
    ? data.source_entry_ids.length
    : null;
  const { lastUserInput, summary } = compactionContent(entry);

  return (
    <article className="context-card context-card--compaction">
      <header className="context-card__head">
        <span className="context-card__seal" aria-hidden="true">
          <Icon name="layers" size={15} />
        </span>
        <div className="context-card__copy">
          <p className="context-card__eyebrow">
            {t("chat.boundary.eyebrow", { id: entry.id })}
          </p>
          <h3>
            {auto
              ? t("chat.boundary.autoCompacted")
              : t("chat.boundary.compacted")}
          </h3>
        </div>
        {auto ? <Badge tone="ochre">{t("chat.boundary.auto")}</Badge> : null}
      </header>

      <p className="context-card__lead">{t("chat.boundary.compactLead")}</p>

      {reason || sourceCount !== null || summaryChars !== null ? (
        <p className="context-card__meta">
          {reason ? <span>{reason}</span> : null}
          {sourceCount !== null ? (
            <span>
              {t(
                sourceCount === 1
                  ? "chat.boundary.foldedOne"
                  : "chat.boundary.foldedOther",
                { count: formatNumber(sourceCount) },
              )}
            </span>
          ) : null}
          {summaryChars !== null ? (
            <span>
              {t("chat.boundary.summaryChars", {
                count: formatNumber(summaryChars),
              })}
            </span>
          ) : null}
        </p>
      ) : null}

      {lastUserInput ? (
        <div className="context-card__block">
          <p className="context-card__label">
            {t("chat.boundary.lastUserInput")}
          </p>
          <p className="context-card__last">{lastUserInput}</p>
        </div>
      ) : null}

      {summary ? (
        <details className="context-card__details">
          <summary>
            <span>{t("chat.boundary.summary")}</span>
            <Icon name="chevron-down" size={13} />
          </summary>
          <p className="context-card__summary">{summary}</p>
        </details>
      ) : (
        <p className="context-card__fallback">
          {t("chat.boundary.summaryFallback")}
        </p>
      )}
    </article>
  );
}

function ResetCard({ entry }: { readonly entry: AgentEntrySchema }) {
  const { t } = useI18n();
  const data = isRecord(entry.data) ? entry.data : {};
  const reason = reasonLabel(stringValue(data.reason), t);

  return (
    <article className="context-card context-card--reset">
      <header className="context-card__head">
        <span className="context-card__seal" aria-hidden="true">
          <Icon name="archive" size={15} />
        </span>
        <div className="context-card__copy">
          <p className="context-card__eyebrow">
            {t("chat.boundary.eyebrow", { id: entry.id })}
          </p>
          <h3>{t("chat.boundary.cleared")}</h3>
        </div>
        {reason ? <Badge tone="ochre">{reason}</Badge> : null}
      </header>

      <p className="context-card__lead">{t("chat.boundary.resetLead")}</p>
      <p className="context-card__note">{t("chat.boundary.resetNote")}</p>
    </article>
  );
}

/** A visible boundary where the active model context restarts. */
export function ContextBoundaryCard({
  entry,
}: {
  readonly entry: AgentEntrySchema;
}) {
  if (entry.kind === "pi.compaction") {
    return <CompactionCard entry={entry} />;
  }
  if (entry.kind === "pi.reset") {
    return <ResetCard entry={entry} />;
  }
  return null;
}
