import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { truncate } from "../../../lib/format";
import { Icon, type IconName } from "../../component/Icon";
import { useGetAgentHistoryMessage } from "../../generated-apis-types/agent/agent";
import { useGetFile } from "../../generated-apis-types/files/files";
import { useReadMemory } from "../../generated-apis-types/memories/memories";
import { useI18n, type Translate } from "../../i18n";
import {
  citationHref,
  citationLabel,
  type CitationToken,
} from "../types";
import { useWebSources, webDomainLabel, type WebSource } from "../web-sources";

const CITATION_ICONS: Record<CitationToken["kind"], IconName> = {
  file: "file",
  memory: "memory",
  summary: "layers",
  history: "history",
  web: "external",
};

interface CitationPresentation {
  readonly text: ReactNode;
  readonly accessibleLabel: string;
  readonly chipTitle: string | undefined;
}

interface CitationPresentationInput {
  readonly label: ReactNode;
  readonly fileTitle: string | null;
  readonly memoryTitle: string | null;
  readonly historyExcerpt: string | null;
  readonly historyTooltip: string | null;
}

function presentCitation(
  token: CitationToken,
  t: Translate,
  values: CitationPresentationInput,
): CitationPresentation {
  if (token.kind === "file") {
    // File citations are for people: show the cited file's name, while the
    // agent keeps the stable [file:id] token in its prose and every link still
    // resolves to the same Library file and chunk.
    const text = values.fileTitle
      ? t("chat.citation.fileTitle", { title: values.fileTitle })
      : t("chat.citation.fileId", { id: token.id });
    return { text, accessibleLabel: text, chipTitle: text };
  }
  if (token.kind === "memory") {
    // Memory citations are for people: show the generated summary, while the
    // agent keeps the stable [memory:id] token in its prose and every link still
    // resolves to /library/memories/{id}.
    const text = values.memoryTitle
      ? t("chat.citation.memoryTitle", { title: values.memoryTitle })
      : t("chat.citation.memoryId", { id: token.id });
    const accessibleLabel = values.memoryTitle
      ? `${citationLabel(token)} · ${values.memoryTitle}`
      : citationLabel(token);
    return {
      text,
      accessibleLabel,
      chipTitle: values.memoryTitle ?? undefined,
    };
  }
  if (token.kind === "history") {
    // A history citation shows the cited message itself once it loads. The
    // stable token stays in the accessible name, and the conversation/excerpt
    // tooltip identifies where the message came from.
    const text = values.historyExcerpt
      ? t("chat.citation.historyExcerpt", { excerpt: values.historyExcerpt })
      : t("chat.citation.historyId", { id: token.id });
    const accessibleLabel = values.historyTooltip
      ? `${citationLabel(token)} · ${values.historyTooltip}`
      : citationLabel(token);
    return {
      text,
      accessibleLabel,
      chipTitle: values.historyTooltip ?? citationLabel(token),
    };
  }
  return {
    text: values.label ?? citationLabel(token),
    accessibleLabel: citationLabel(token),
    chipTitle: undefined,
  };
}

interface CitationChipProps {
  readonly token: CitationToken;
  readonly label?: ReactNode;
  /** A known file name; when present, skip the metadata query. */
  readonly fileTitle?: string | null;
  /** The memory's auto-generated name, shown after the numeric citation. */
  readonly memoryTitle?: string | null;
  /** When present, the chip opens an in-app surface instead of navigating. */
  readonly onOpen?: (token: CitationToken) => void;
  /**
   * Replaces the kind icon in the fixed leading slot (for example a tiny file
   * thumbnail). The slot keeps the icon's size so a late image never reflows
   * the sentence around the chip.
   */
  readonly leading?: ReactNode;
}

/**
 * A `[web:wN]` citation: the page's domain as a chip that opens the page in a
 * new tab. The full title and URL are in the tooltip. An unresolved number
 * (for example a label pasted from another conversation) stays a plain label.
 */
function WebCitationChip({
  token,
  source,
}: {
  readonly token: CitationToken;
  readonly source: WebSource | undefined;
}) {
  const { t } = useI18n();
  const label = citationLabel(token);
  if (!source) {
    return (
      <span
        className="citation-chip web"
        title={t("chat.citation.webUnknown", { label })}
      >
        <Icon name={CITATION_ICONS.web} size={11} />
        <span className="citation-chip__label">{label}</span>
      </span>
    );
  }
  const domain = webDomainLabel(source.url);
  const tooltip = source.title ? `${source.title}\n${source.url}` : source.url;
  return (
    <a
      className="citation-chip web"
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      title={tooltip}
      aria-label={t("chat.citation.webOpen", {
        title: source.title ?? domain,
        label,
      })}
    >
      <Icon name={CITATION_ICONS.web} size={11} />
      <span className="citation-chip__label">{domain}</span>
    </a>
  );
}

/** A citation token rendered as a preview trigger or a resolved link. */
export function CitationChip(props: CitationChipProps) {
  const webSources = useWebSources();
  if (props.token.kind === "web") {
    return (
      <WebCitationChip
        token={props.token}
        source={webSources.get(props.token.id)}
      />
    );
  }
  return <ArchiveCitationChip {...props} />;
}

function ArchiveCitationChip({
  token,
  label,
  fileTitle,
  memoryTitle,
  onOpen,
  leading,
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
  const historyQuery = useGetAgentHistoryMessage(token.id, {
    query: {
      enabled: token.kind === "history",
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
  const historyMessage =
    token.kind === "history" ? historyQuery.data : undefined;
  const historyContent = historyMessage?.content.trim() ?? "";
  const historyExcerpt =
    historyContent.length > 0 ? truncate(historyContent, 48) : null;
  const historyTooltip =
    historyMessage && historyContent.length > 0
      ? `${historyMessage.conversation_title} · ${truncate(historyContent, 200)}`
      : null;
  const { text, accessibleLabel, chipTitle } = presentCitation(token, t, {
    label,
    fileTitle: resolvedFileTitle,
    memoryTitle: resolvedMemoryTitle ?? null,
    historyExcerpt,
    historyTooltip,
  });
  const className = `citation-chip ${token.kind}`;
  const content = (
    <>
      {leading ?? <Icon name={CITATION_ICONS[token.kind]} size={11} />}
      <span className="citation-chip__label" title={chipTitle}>
        {text}
      </span>
    </>
  );

  if (onOpen && (token.kind === "file" || token.kind === "memory")) {
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

  const href =
    token.kind === "history" && historyMessage
      ? `/chat/${historyMessage.conversation_id}#entry-${historyMessage.entry_id}`
      : citationHref(token);
  if (href) {
    return (
      <Link
        className={className}
        to={href}
        title={
          token.kind === "history"
            ? chipTitle
            : t("chat.common.open", { label: accessibleLabel })
        }
        aria-label={token.kind === "history" ? accessibleLabel : undefined}
      >
        {content}
      </Link>
    );
  }

  return (
    <span
      className={className}
      title={token.kind === "history" ? chipTitle : accessibleLabel}
    >
      {content}
    </span>
  );
}
