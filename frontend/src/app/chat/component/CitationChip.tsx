import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../component/Icon";
import { useReadMemory } from "../../generated-apis-types/memories/memories";
import { useI18n } from "../../i18n";
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
  /** The memory's auto-generated name, shown after the numeric citation. */
  readonly memoryTitle?: string | null;
  /** When present, the chip opens an in-app surface instead of navigating. */
  readonly onOpen?: (token: CitationToken) => void;
}

/** A citation token rendered as a preview trigger or a library/memory link. */
export function CitationChip({
  token,
  label,
  memoryTitle,
  onOpen,
}: CitationChipProps) {
  const { t } = useI18n();
  const needsMemoryTitle = token.kind === "memory" && !memoryTitle;
  const memoryQuery = useReadMemory(
    token.id,
    { memory_range: 0, trace_history: false },
    {
      query: {
        enabled: needsMemoryTitle,
        retry: false,
        staleTime: 60_000,
      },
    },
  );
  const resolvedTitle =
    memoryTitle ??
    (token.kind === "memory" ? memoryQuery.data?.target.title : undefined);
  const accessibleLabel = resolvedTitle
    ? `${citationLabel(token)} · ${resolvedTitle}`
    : citationLabel(token);
  // Memory citations are for people: show the generated summary, while the
  // agent keeps the stable [memory:id] token in its prose and every link still
  // resolves to /memory/{id}.
  let text = label ?? citationLabel(token);
  if (token.kind === "memory") {
    text = resolvedTitle
      ? t("chat.citation.memoryTitle", { title: resolvedTitle })
      : t("chat.citation.memoryId", { id: token.id });
  }
  const className = `citation-chip ${token.kind}`;
  const content = (
    <>
      <Icon name={CITATION_ICONS[token.kind]} size={11} />
      <span className="citation-chip__label" title={resolvedTitle}>
        {text}
      </span>
    </>
  );

  if (onOpen && token.kind !== "summary") {
    return (
      <button
        type="button"
        className={className}
        onClick={() => onOpen(token)}
        title={t("chat.common.open", { label: accessibleLabel })}
      >
        {content}
      </button>
    );
  }

  const href = citationHref(token);
  if (href) {
    return (
      <Link
        className={className}
        to={href}
        title={t("chat.common.open", { label: accessibleLabel })}
      >
        {content}
      </Link>
    );
  }

  return (
    <span className={className} title={accessibleLabel}>
      {content}
    </span>
  );
}
