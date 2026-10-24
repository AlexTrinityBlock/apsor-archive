import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../component/Icon";
import {
  citationHref,
  citationLabel,
  type CitationToken,
} from "../types";

const CITATION_ICONS: Record<CitationToken["kind"], IconName> = {
  file: "file",
  memory: "memory",
  summary: "layers",
};

interface CitationChipProps {
  readonly token: CitationToken;
  readonly label?: ReactNode;
  /** When present, the chip opens an in-app surface instead of navigating. */
  readonly onOpen?: (token: CitationToken) => void;
}

/** A citation token rendered as a preview trigger or a library/memory link. */
export function CitationChip({ token, label, onOpen }: CitationChipProps) {
  const text = label ?? citationLabel(token);
  const className = `citation-chip ${token.kind}`;
  const content = (
    <>
      <Icon name={CITATION_ICONS[token.kind]} size={11} />
      <span>{text}</span>
    </>
  );

  if (onOpen && token.kind !== "summary") {
    return (
      <button
        type="button"
        className={className}
        onClick={() => onOpen(token)}
        title={`Open ${citationLabel(token)}`}
      >
        {content}
      </button>
    );
  }

  const href = citationHref(token);
  if (href) {
    return (
      <Link className={className} to={href} title={`Open ${citationLabel(token)}`}>
        {content}
      </Link>
    );
  }

  return (
    <span className={className} title={citationLabel(token)}>
      {content}
    </span>
  );
}
