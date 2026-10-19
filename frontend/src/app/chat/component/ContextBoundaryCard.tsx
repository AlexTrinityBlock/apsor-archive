import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import { isRecord, numberValue, stringValue, userText } from "../types";

const SUMMARY_FALLBACK = "Summary stored in the context boundary.";

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

function reasonLabel(reason: string | null): string | null {
  if (!reason) {
    return null;
  }
  if (reason === "manual") {
    return "Manual compaction";
  }
  if (reason === "auto_context_threshold") {
    return "Context threshold reached";
  }
  if (reason === "manual_clear") {
    return "Manual clear";
  }
  return reason.replaceAll("_", " ");
}

function CompactionCard({ entry }: { readonly entry: AgentEntrySchema }) {
  const data = isRecord(entry.data) ? entry.data : {};
  const auto = data.auto === true;
  const reason = reasonLabel(stringValue(data.reason));
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
            Context boundary · entry {entry.id}
          </p>
          <h3>{auto ? "Auto-compacted" : "Context compacted"}</h3>
        </div>
        {auto ? <Badge tone="ochre">Auto</Badge> : null}
      </header>

      <p className="context-card__lead">
        Earlier turns were folded into this boundary. The full transcript is
        still preserved here; the model sees the summary instead.
      </p>

      {reason || sourceCount !== null || summaryChars !== null ? (
        <p className="context-card__meta">
          {reason ? <span>{reason}</span> : null}
          {sourceCount !== null ? (
            <span>
              {formatNumber(sourceCount)}{" "}
              {sourceCount === 1 ? "entry" : "entries"} folded
            </span>
          ) : null}
          {summaryChars !== null ? (
            <span>{formatNumber(summaryChars)} summary chars</span>
          ) : null}
        </p>
      ) : null}

      {lastUserInput ? (
        <div className="context-card__block">
          <p className="context-card__label">Last user input</p>
          <p className="context-card__last">{lastUserInput}</p>
        </div>
      ) : null}

      {summary ? (
        <details className="context-card__details">
          <summary>
            <span>Summary</span>
            <Icon name="chevron-down" size={13} />
          </summary>
          <p className="context-card__summary">{summary}</p>
        </details>
      ) : (
        <p className="context-card__fallback">{SUMMARY_FALLBACK}</p>
      )}
    </article>
  );
}

function ResetCard({ entry }: { readonly entry: AgentEntrySchema }) {
  const data = isRecord(entry.data) ? entry.data : {};
  const reason = reasonLabel(stringValue(data.reason));

  return (
    <article className="context-card context-card--reset">
      <header className="context-card__head">
        <span className="context-card__seal" aria-hidden="true">
          <Icon name="archive" size={15} />
        </span>
        <div className="context-card__copy">
          <p className="context-card__eyebrow">
            Context boundary · entry {entry.id}
          </p>
          <h3>Context cleared</h3>
        </div>
        {reason ? <Badge tone="ochre">{reason}</Badge> : null}
      </header>

      <p className="context-card__lead">
        Older transcript entries are preserved here, but they are no longer
        sent to the model.
      </p>
      <p className="context-card__note">
        The next message starts from an empty active context. Nothing in the
        reading view was deleted.
      </p>
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
