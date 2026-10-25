import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import {
  citationLabel,
  parseCitationLabel,
  type CitationToken,
} from "../../chat/types";
import { useI18n } from "../../i18n";

interface QuestionCitationsProps {
  readonly citations: readonly string[];
  readonly className?: string;
}

function parseSavedCitation(label: string): CitationToken | null {
  const trimmed = label.trim();
  if (trimmed.length === 0) {
    return null;
  }
  return parseCitationLabel(trimmed.startsWith("[") ? trimmed : `[${trimmed}]`);
}

function fileHref(token: CitationToken): string {
  const params = new URLSearchParams({ tab: "files", file: String(token.id) });
  if (token.chunk !== null) {
    params.set("chunk", String(token.chunk));
  }
  return `/library?${params.toString()}`;
}

function CitationTokenChip({ label }: { readonly label: string }) {
  const { t } = useI18n();
  const token = parseSavedCitation(label);

  if (!token) {
    return (
      <span
        className="citation-chip question-citation question-citation--raw"
        title={t("memory.questions.citations.unrecognised")}
      >
        {label}
      </span>
    );
  }

  if (token.kind === "file") {
    const text = citationLabel(token);
    return (
      <Link
        className="citation-chip file question-citation"
        to={fileHref(token)}
        title={t("memory.questions.citations.openFile", { label: text })}
      >
        <Icon name="file" size={11} />
        <span>{text}</span>
      </Link>
    );
  }

  if (token.kind === "memory") {
    const text = citationLabel(token);
    return (
      <Link
        className="citation-chip memory question-citation"
        to={`/memory/${token.id}`}
        title={t("memory.questions.citations.openMemory", { label: text })}
      >
        <Icon name="memory" size={11} />
        <span>{text}</span>
      </Link>
    );
  }

  if (token.kind === "summary") {
    const text = citationLabel(token);
    return (
      <details className="question-citation-more">
        <summary
          className="citation-chip question-citation question-citation--summary"
          title={t("memory.questions.citations.expandSummary")}
        >
          <Icon name="layers" size={11} />
          <span>{text}</span>
        </summary>
        <p className="question-citation-more__body">
          {t("memory.questions.citations.summaryBody")}
        </p>
      </details>
    );
  }

  return (
    <span
      className="citation-chip question-citation question-citation--media"
      title={t("memory.questions.citations.mediaTitle")}
    >
      <Icon name="ring" size={11} />
      <span>{citationLabel(token)}</span>
    </span>
  );
}

/** Citation receipts attached to a saved answer. */
export function QuestionCitations({
  citations,
  className,
}: QuestionCitationsProps) {
  const { t } = useI18n();

  if (citations.length === 0) {
    return null;
  }
  return (
    <div className={["question-card__citations", className].filter(Boolean).join(" ")}>
      <p className="mono-label">{t("memory.questions.citations.label")}</p>
      <div className="question-card__chips">
        {citations.map((label, index) => (
          <CitationTokenChip key={`${label}:${index}`} label={label} />
        ))}
      </div>
    </div>
  );
}
