import { lazy, Suspense, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useI18n } from "../../i18n";
import {
  classifyFile,
  fileContentUrl,
  kindLabel,
  type ViewerKind,
} from "../../viewer/component/viewer-utils";
import { resourceHref, type ResourceMeta } from "../types";

const RESOURCE_ICONS: Record<ResourceMeta["resourceType"], IconName> = {
  file: "file",
  memory: "memory",
};

const RESOURCE_LABEL_KEYS = {
  file: "chat.resource.file",
  memory: "chat.resource.memory",
} as const;

const PRESENTED_LABEL_KEYS = {
  file: "chat.resource.presentedFile",
  memory: "chat.resource.presentedMemory",
} as const;

const ResourcePdfThumb = lazy(() =>
  import("./ResourcePdfThumb").then((module) => ({
    default: module.ResourcePdfThumb,
  })),
);

function FileTile({
  icon,
  badge,
  title,
}: {
  readonly icon: IconName;
  readonly badge: string;
  readonly title: string;
}) {
  return (
    <span
      className="chat-resource__thumb chat-resource__thumb--file"
      aria-hidden="true"
      title={title}
    >
      <Icon name={icon} size={56} />
      <span className="chat-resource__badge">{badge}</span>
    </span>
  );
}

function extensionOf(title: string | null): string {
  if (!title) {
    return "";
  }
  const match = /\.[^./\\]+$/.exec(title);
  return match ? match[0].toLowerCase() : "";
}

function thumbnailBadge(kind: ViewerKind, title: string | null): string {
  switch (kind) {
    case "pdf":
      return "PDF";
    case "docx":
      return "DOC";
    case "pptx":
      return "PPT";
    case "spreadsheet":
      return "XLS";
    case "image":
      return "IMG";
    case "markdown":
      return "MD";
    case "json":
      return "JSON";
    case "csv":
      return "CSV";
    case "text":
      return "TXT";
    default: {
      const extension = extensionOf(title).replace(".", "").slice(0, 4);
      return extension.length > 0 ? extension.toUpperCase() : "FILE";
    }
  }
}

function ResourceThumb({
  resource,
  kind,
}: {
  readonly resource: ResourceMeta;
  readonly kind: ViewerKind | null;
}) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const resourceId = resource.resourceId;
  const isImage = kind === "image" && resourceId !== null;
  const title = resource.title ?? t(RESOURCE_LABEL_KEYS[resource.resourceType]);

  if (isImage && !failed) {
    return (
      <span className="chat-resource__thumb chat-resource__thumb--image">
        {imageLoaded ? null : (
          <span className="chat-resource__thumb-loading" aria-hidden="true">
            <Loader size={18} className="chat-resource__thumb-loader" />
          </span>
        )}
        <img
          src={fileContentUrl(resourceId)}
          alt=""
          loading="lazy"
          decoding="async"
          onLoad={() => setImageLoaded(true)}
          onError={() => setFailed(true)}
        />
      </span>
    );
  }

  let icon: IconName = RESOURCE_ICONS.file;
  if (resource.resourceType === "memory") {
    icon = RESOURCE_ICONS.memory;
  } else if (kind === "image") {
    icon = "image";
  }
  const badge =
    resource.resourceType === "memory"
      ? t("chat.resource.memoryBadge")
      : thumbnailBadge(kind ?? "unsupported", resource.title);
  const tile = <FileTile icon={icon} badge={badge} title={title} />;

  // A PDF shows its first page instead of a generic file tile. The lazy chunk
  // keeps pdf.js out of the transcript until a PDF is actually presented.
  if (resource.resourceType === "file" && kind === "pdf" && resourceId !== null) {
    if (failed) {
      return tile;
    }
    return (
      <Suspense fallback={tile}>
        <ResourcePdfThumb
          fileId={resourceId}
          onError={() => setFailed(true)}
        />
      </Suspense>
    );
  }

  return tile;
}

interface ResourceCardProps {
  readonly resource: ResourceMeta;
  /** When present, the card opens the in-chat preview dialog. */
  readonly onOpen?: (resource: ResourceMeta) => void;
}

/**
 * A presented file or memory as a compact preview bubble.
 *
 * Images and the first page of a PDF show a real preview; every other kind
 * uses a type tile. The whole bubble is the preview trigger, so the chat
 * transcript never needs to send the reader to another page just to recognise
 * what the agent presented.
 */
export function ResourceCard({ resource, onOpen }: ResourceCardProps) {
  const { t } = useI18n();
  const resourceLabel = t(RESOURCE_LABEL_KEYS[resource.resourceType]);
  const title =
    resource.title ??
    `${resourceLabel} ${
      resource.resourceId === null ? "" : `#${resource.resourceId}`
    }`.trim();
  const extension = extensionOf(resource.title);
  const kind =
    resource.resourceType === "file"
      ? classifyFile({
          mime_type: resource.mimeType ?? "",
          extension,
        })
      : null;
  const details = [
    kind === null ? null : kindLabel(kind, t),
    kind === "unsupported" ? resource.mimeType : null,
    resource.chunk === null
      ? null
      : t("chat.common.chunk", { chunk: resource.chunk }),
  ].filter(
    (item): item is string => item !== null && item.length > 0,
  );
  const href = resourceHref(resource);
  const actionable = onOpen !== undefined || href !== null;
  const actionLabel =
    resource.resourceType === "file"
      ? t("chat.resource.preview")
      : t("chat.resource.openMemory");
  const fallbackDetail =
    resource.resourceType === "memory"
      ? t("chat.resource.openMemory")
      : t("chat.resource.previewHint");

  const body = (
    <>
      <span className="chat-resource__preview">
        <ResourceThumb resource={resource} kind={kind} />
      </span>
      <span className="chat-resource__body">
        <span className="chat-resource__body-text">
          <span className="mono-label">
            {t(PRESENTED_LABEL_KEYS[resource.resourceType])}
          </span>
          <span className="chat-resource__title">{title}</span>
          <span className="chat-resource__meta">
            {details.length > 0 ? details.join(" · ") : fallbackDetail}
          </span>
        </span>
        {actionable ? (
          <span className="chat-resource__action" aria-hidden="true">
            <span>{actionLabel}</span>
            <Icon name={onOpen ? "maximize" : "arrow-up-right"} size={13} />
          </span>
        ) : null}
      </span>
    </>
  );

  let card: ReactNode;
  if (onOpen) {
    card = (
      <button
        type="button"
        className="chat-resource"
        onClick={() => onOpen(resource)}
        aria-label={t("chat.resource.previewAria", { title })}
        title={t("chat.resource.preview")}
      >
        {body}
      </button>
    );
  } else if (href) {
    card = (
      <Link className="chat-resource" to={href} aria-label={actionLabel}>
        {body}
      </Link>
    );
  } else {
    card = (
      <span className="chat-resource is-static" aria-label={actionLabel}>
        {body}
      </span>
    );
  }

  return <div className="chat-resource-row">{card}</div>;
}
