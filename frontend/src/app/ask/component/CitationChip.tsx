import { Link } from "react-router-dom";

import type { CitationSchema, CitationSchemaKind } from "../../generated-apis-types/schemas";
import { Icon, type IconName } from "../../component/Icon";
import { fileCitationHref, memoryCitationHref } from "./citationLinks";

const KIND_ICONS: Record<CitationSchemaKind, IconName> = {
  file: "file",
  memory: "memory",
  summary: "layers",
};

interface CitationChipProps {
  readonly citation: CitationSchema;
  readonly onSummaryClick: (citation: CitationSchema) => void;
}

function chipClassName(citation: CitationSchema): string {
  return [
    "ask-citation",
    `ask-citation--${citation.kind}`,
    citation.cited ? "is-cited" : "is-retrieved",
  ].join(" ");
}

function chipContent(citation: CitationSchema) {
  return (
    <>
      <Icon name={KIND_ICONS[citation.kind]} size={11} />
      <span>[{citation.label}]</span>
    </>
  );
}

/**
 * A citation token rendered as a real link where the archive can resolve it.
 * Summary citations are buttons because their destination is the rail card.
 */
export function CitationChip({ citation, onSummaryClick }: CitationChipProps) {
  const className = chipClassName(citation);
  const label = `[${citation.label}]`;

  if (citation.kind === "file") {
    const href = fileCitationHref(citation);
    if (href !== null) {
      return (
        <Link
          className={className}
          to={href}
          title={citation.raw_file_path ?? label}
          aria-label={`Open cited file ${citation.label}`}
        >
          {chipContent(citation)}
        </Link>
      );
    }
  }

  if (citation.kind === "memory") {
    const href = memoryCitationHref(citation);
    if (href !== null) {
      return (
        <Link
          className={className}
          to={href}
          aria-label={`Open cited memory ${citation.label}`}
        >
          {chipContent(citation)}
        </Link>
      );
    }
  }

  if (citation.kind === "summary") {
    return (
      <button
        type="button"
        className={className}
        onClick={() => onSummaryClick(citation)}
        aria-label={`Reveal cited summary ${citation.label}`}
      >
        {chipContent(citation)}
      </button>
    );
  }

  return (
    <span className={className} title={citation.label}>
      {chipContent(citation)}
    </span>
  );
}
