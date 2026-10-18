import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { formatNumber } from "../../../lib/format";
import {
  MAX_PAGE_CONTEXT_CHARS,
  type PageContextSnapshot,
} from "../page-context";

interface PageContextBarProps {
  readonly context: PageContextSnapshot | null;
  readonly lastKey: string | null;
  readonly conversationId: number | null;
}

/**
 * The context strip above a dock composer.
 *
 * It shows exactly what will be sent and whether this page is already attached
 * to the conversation. The copy is intentionally quiet once attached, so a
 * repeated question never looks like a new context insertion.
 */
export function PageContextBar({
  context,
  lastKey,
  conversationId,
}: PageContextBarProps) {
  if (!context) {
    return (
      <div className="pi-context-bar pi-context-bar--empty">
        <Icon name="info" size={13} />
        <span>No readable page text was found for this view.</span>
      </div>
    );
  }

  const attached = lastKey === context.key;
  let stateLabel = "Will attach on the next note";
  if (attached) {
    stateLabel = "Attached to this conversation";
  } else if (conversationId === null) {
    stateLabel = "Attaches when this thread opens";
  } else if (lastKey !== null) {
    stateLabel = "New page · will attach on the next note";
  }

  return (
    <details className={attached ? "pi-context-bar is-attached" : "pi-context-bar"}>
      <summary className="pi-context-bar__summary">
        <span className="pi-context-bar__mark" aria-hidden="true">
          <Icon name="layers" size={13} />
        </span>
        <span className="pi-context-bar__copy">
          <span className="pi-context-bar__eyebrow">Current page context</span>
          <span className="pi-context-bar__title">
            {context.title ?? context.path}
          </span>
          <code className="pi-context-bar__path">{context.path}</code>
        </span>
        <span className="pi-context-bar__state">
          {attached ? <Badge tone="moss">attached</Badge> : null}
          <span className="pi-context-bar__chars">
            {formatNumber(context.text.length)} / {formatNumber(MAX_PAGE_CONTEXT_CHARS)}
          </span>
          <Icon name="chevron-down" size={12} />
        </span>
      </summary>

      <div className="pi-context-bar__body">
        <p className="pi-context-bar__state-line">
          {stateLabel}
          {context.truncated ? " · text trimmed at the archive cap" : ""}
        </p>
        <p className="pi-context-bar__note">
          Only changes are added to the conversation. Asking again from this
          page reuses the captured snapshot.
        </p>
        <pre className="pi-context-bar__text">{context.text}</pre>
      </div>
    </details>
  );
}
