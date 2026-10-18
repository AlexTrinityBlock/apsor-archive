import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import { readPageContextEntry } from "../page-context";

/**
 * A captured page snapshot in the transcript.
 *
 * This is deliberately not a user marginalium: the keeper did not write it,
 * and it is excluded from user-message counts. The full text is expandable
 * because the model receives it as a data envelope.
 */
export function PageContextCard({ entry }: { readonly entry: AgentEntrySchema }) {
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
            Page context · captured
            {context.truncated ? <Badge tone="ochre">trimmed</Badge> : null}
          </span>
          <span className="pi-context-card__title">
            {context.title ?? context.path}
          </span>
          <code className="pi-context-card__path">{context.path}</code>
        </span>
        <span className="pi-context-card__meta">
          {formatNumber(context.textChars)} chars
          <Icon name="chevron-down" size={13} />
        </span>
      </summary>
      <div className="pi-context-card__body">
        <p className="pi-context-card__note">
          A plain-text snapshot was added once when the page changed. The
          transcript keeps it as an append-only context entry.
        </p>
        {context.text.length > 0 ? (
          <pre className="pi-context-card__text">{context.text}</pre>
        ) : (
          <p className="pi-context-card__empty">
            The provider envelope is recorded, but its text could not be
            decoded in this browser.
          </p>
        )}
      </div>
    </details>
  );
}
