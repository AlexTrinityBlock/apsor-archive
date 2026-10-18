import { Link } from "react-router-dom";

import type {
  CitationSchema,
  CitationSchemaKind,
} from "../../generated-apis-types/schemas";
import { formatDateTime } from "../../../lib/format";
import { highlightTerms, snippetAround } from "../../../lib/highlight";
import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import type { BadgeTone } from "../../type/ui";
import {
  fileCitationHref,
  memoryCitationHref,
  summarySourceId,
} from "./citationLinks";
import type { AskTurn } from "./types";

const KIND_TONES: Record<CitationSchemaKind, BadgeTone> = {
  file: "moss",
  memory: "vermilion",
  summary: "ochre",
};

const EXCERPT_LIMIT = 240;

interface SourceCardProps {
  readonly citation: CitationSchema;
  readonly question: string;
  readonly onSummaryClick: (citation: CitationSchema) => void;
}

function SourceCard({ citation, question, onSummaryClick }: SourceCardProps) {
  const targetId = summarySourceId(citation);
  const fileHref = fileCitationHref(citation);
  const memoryHref = memoryCitationHref(citation);
  const className = [
    "ask-source",
    citation.cited ? "is-cited" : "is-retrieved",
  ].join(" ");

  return (
    <article className={className} id={targetId ?? undefined}>
      <header className="ask-source__head">
        <Badge tone={KIND_TONES[citation.kind]}>{citation.kind}</Badge>
        <span className="ask-source__label">[{citation.label}]</span>
        {citation.cited ? (
          <Badge tone="moss" dot className="ask-source__cited">
            cited
          </Badge>
        ) : null}
      </header>

      {citation.raw_file_path ? (
        <span className="ask-source__path">{citation.raw_file_path}</span>
      ) : null}

      <p className="ask-source__excerpt">
        {highlightTerms(
          snippetAround(citation.excerpt, question, EXCERPT_LIMIT),
          question,
        )}
      </p>

      <footer className="ask-source__foot">
        <time dateTime={citation.time}>{formatDateTime(citation.time)}</time>
        {fileHref ? (
          <Link className="ask-source__action" to={fileHref}>
            Open file
            <Icon name="arrow-up-right" size={12} />
          </Link>
        ) : null}
        {memoryHref ? (
          <Link className="ask-source__action" to={memoryHref}>
            Trace memory
            <Icon name="arrow-up-right" size={12} />
          </Link>
        ) : null}
        {targetId ? (
          <button
            type="button"
            className="ask-source__action ask-source__action--summary"
            onClick={() => onSummaryClick(citation)}
          >
            Locate
            <Icon name="arrow-down" size={12} />
          </button>
        ) : null}
      </footer>
    </article>
  );
}

function retrievalLabel(turn: AskTurn | null): string {
  if (!turn) {
    return "Nothing retrieved yet";
  }
  const count = turn.citations.length;
  return `${count} retrieved ${count === 1 ? "passage" : "passages"}`;
}

interface SourcesRailProps {
  readonly turn: AskTurn | null;
  readonly onSummaryClick: (citation: CitationSchema) => void;
}

/** The right-hand ledger of every passage behind the latest answer. */
export function SourcesRail({ turn, onSummaryClick }: SourcesRailProps) {
  const citedCount = turn
    ? turn.citations.filter((citation) => citation.cited).length
    : 0;

  return (
    <aside className="ask-sources" aria-labelledby="ask-sources-title">
      <div className="ask-sources__inner">
        <header className="ask-sources__head">
          <p className="eyebrow">Sources · latest answer</p>
          <div className="ask-sources__head-row">
            <h2 id="ask-sources-title">Sources</h2>
            {turn ? <Badge tone="moss">{citedCount} cited</Badge> : null}
          </div>
          <p className="ask-sources__count">{retrievalLabel(turn)}</p>
        </header>

        {!turn ? (
          <div className="ask-sources__empty">
            <Icon name="quote" size={20} />
            <p>
              Ask a question to open its citation ledger. The latest answer keeps
              every retrieved passage here, with cited sources lifted above the
              rest.
            </p>
          </div>
        ) : null}

        {turn && turn.citations.length === 0 ? (
          <p className="ask-sources__empty-text">
            The archive did not return a source for this answer. Nothing has been
            invented to fill the gap.
          </p>
        ) : null}

        {turn && turn.citations.length > 0 ? (
          <div className="ask-sources__list">
            {turn.citations.map((citation) => (
              <SourceCard
                key={citation.label}
                citation={citation}
                question={turn.question}
                onSummaryClick={onSummaryClick}
              />
            ))}
          </div>
        ) : null}

        <p className="ask-sources__grounding">
          <Icon name="ring" size={14} />
          Grounded by 2–4 retrieval steps.
        </p>
      </div>
    </aside>
  );
}
