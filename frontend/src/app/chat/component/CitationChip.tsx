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
  media: "ring",
  summary: "layers",
};

interface CitationChipProps {
  readonly token: CitationToken;
  readonly label?: ReactNode;
}

/** A citation token rendered as a viewer link when the kind has one. */
export function CitationChip({ token, label }: CitationChipProps) {
  const text = label ?? citationLabel(token);
  const className = `chat-citation chat-citation--${token.kind}`;
  const content = (
    <>
      <Icon name={CITATION_ICONS[token.kind]} size={10} />
      <span>{text}</span>
    </>
  );
  const href = citationHref(token);

  if (href) {
    return (
      <Link
        className={className}
        to={href}
        title={`Open ${citationLabel(token)}`}
      >
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
