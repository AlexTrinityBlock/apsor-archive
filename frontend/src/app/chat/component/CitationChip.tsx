import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../component/Icon";
import { useGetFile } from "../../generated-apis-types/files/files";
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
  /** A known file name; when present, skip the metadata query. */
  readonly fileTitle?: string | null;
  /** The memory's auto-generated name, shown after the numeric citation. */
  readonly memoryTitle?: string | null;
  /** When present, the chip opens an in-app surface instead of navigating. */
  readonly onOpen?: (token: CitationToken) => void;
}

/** A citation token rendered as a preview trigger or a library/memory link. */
export function CitationChip({
  token,
  label,
  fileTitle,
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
  const fileQuery = useGetFile(token.id, {
    query: {
      enabled: token.kind === "file" && !fileTitle,
      retry: false,
      staleTime: 60_000,
    },
  });
  const resolvedMemoryTitle =
    memoryTitle ??
    (token.kind === "memory" ? memoryQuery.data?.target.title : undefined);
  const resolvedFileTitle =
    token.kind === "file"
      ? fileTitle ?? fileQuery.data?.file_name ?? null
      : null;

  let accessibleLabel: string;
  let fileText: string | null = null;
  let text: ReactNode;
  if (token.kind === "file") {
    // File citations are for people: show the cited file's name, while the
    // agent keeps the stable [file:id] token in its prose and every link still
    // resolves to the same Library file and chunk.
    fileText = resolvedFileTitle
      ? t("chat.citation.fileTitle", { title: resolvedFileTitle })
      : t("chat.citation.fileId", { id: token.id });
    text = fileText;
    accessibleLabel = fileText;
  } else if (token.kind === "memory") {
    // Memory citations are for people: show the generated summary, while the
    // agent keeps the stable [memory:id] token in its prose and every link still
    // resolves to /memory/{id}.
    text = resolvedMemoryTitle
      ? t("chat.citation.memoryTitle", { title: resolvedMemoryTitle })
      : t("chat.citation.memoryId", { id: token.id });
    accessibleLabel = resolvedMemoryTitle
      ? `${citationLabel(token)} · ${resolvedMemoryTitle}`
      : citationLabel(token);
  } else {
    text = label ?? citationLabel(token);
    accessibleLabel = citationLabel(token);
  }
  const className = `citation-chip ${token.kind}`;
  const chipTitle =
    token.kind === "file" ? fileText ?? undefined : resolvedMemoryTitle;
  const content = (
    <>
      <Icon name={CITATION_ICONS[token.kind]} size={11} />
      <span className="citation-chip__label" title={chipTitle}>
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
