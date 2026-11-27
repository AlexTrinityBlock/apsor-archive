import {
  lazy,
  memo,
  Suspense,
  useCallback,
  useState,
  type ReactNode,
} from "react";
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
import { FileThumbnail } from "../../viewer/component/FileThumbnail";
import type { ThumbnailInfo } from "../../viewer/component/thumbnail";
import { resourceHref, type ResourceMeta } from "../types";
import { framedThumbnailStyle } from "./resource-frame";

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

const TEXT_BADGES: Readonly<Record<string, string>> = {
  ".txt": "TXT",
  ".jsonl": "JSONL",
  ".toml": "TOML",
  ".ini": "INI",
  ".env": "ENV",
  ".log": "LOG",
};

/**
 * The tile badge for a text file: the presented extension when it is one of
 * the known text formats, otherwise the generic `TXT` badge.
 */
export function textThumbnailBadge(title: string | null): string {
  return TEXT_BADGES[extensionOf(title)] ?? "TXT";
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
      return textThumbnailBadge(title);
    default: {
      const extension = extensionOf(title).replace(".", "").slice(0, 4);
      return extension.length > 0 ? extension.toUpperCase() : "FILE";
    }
  }
}

function FramedThumbnail({
  fileId,
  thumbnail,
  title,
  onFailed,
}: {
  readonly fileId: number;
  readonly thumbnail: ThumbnailInfo;
  readonly title: string;
  readonly onFailed?: () => void;
}) {
  return (
    <span
      className="chat-resource__thumb chat-resource__thumb--framed"
      style={framedThumbnailStyle(thumbnail)}
      aria-hidden="true"
      title={title}
    >
      <FileThumbnail
        fileId={fileId}
        thumbnail={thumbnail}
        sizing="fill"
        onError={onFailed}
      />
    </span>
  );
}

/**
 * An image with a server thumbnail: the tiny WebP paints first inside a fixed
 * box and the original fades in over it. A failed original keeps the
 * thumbnail on screen instead of collapsing the card.
 */
function ThumbnailImage({
  fileId,
  thumbnail,
  onFailed,
}: {
  readonly fileId: number;
  readonly thumbnail: ThumbnailInfo;
  readonly onFailed: () => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [originalFailed, setOriginalFailed] = useState(false);
  return (
    <span
      className="chat-resource__thumb chat-resource__thumb--framed"
      style={framedThumbnailStyle(thumbnail)}
    >
      <FileThumbnail
        fileId={fileId}
        thumbnail={thumbnail}
        sizing="fill"
        onError={onFailed}
      >
        {originalFailed ? null : (
          <img
            className={`file-thumbnail__overlay${loaded ? " is-loaded" : ""}`}
            src={fileContentUrl(fileId)}
            alt=""
            loading="lazy"
            decoding="async"
            onLoad={() => setLoaded(true)}
            onError={() => setOriginalFailed(true)}
          />
        )}
      </FileThumbnail>
    </span>
  );
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
  const markFailed = useCallback(() => setFailed(true), []);
  const resourceId = resource.resourceId;
  const isImage = kind === "image" && resourceId !== null;
  const title = resource.title ?? t(RESOURCE_LABEL_KEYS[resource.resourceType]);
  const thumbnail = resource.resourceType === "file" ? resource.thumbnail : null;

  // Order: server thumbnail → original image → PDF page 1 → file tile. A
  // thumbnail fixes the box size up front, so nothing below it can shift.
  if (thumbnail !== null && resourceId !== null && kind !== "pdf" && !failed) {
    if (kind === "image") {
      return (
        <ThumbnailImage
          fileId={resourceId}
          thumbnail={thumbnail}
          onFailed={markFailed}
        />
      );
    }
    return (
      <FramedThumbnail
        fileId={resourceId}
        thumbnail={thumbnail}
        title={title}
        onFailed={markFailed}
      />
    );
  }

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
    if (thumbnail !== null) {
      // The thumbnail is both the Suspense fallback and the layer under the
      // pdf.js canvas, so the box keeps one size from first paint onwards.
      const still = (
        <FramedThumbnail fileId={resourceId} thumbnail={thumbnail} title={title} />
      );
      if (failed) {
        return still;
      }
      return (
        <Suspense fallback={still}>
          <ResourcePdfThumb
            fileId={resourceId}
            thumbnail={thumbnail}
            onError={markFailed}
          />
        </Suspense>
      );
    }
    if (failed) {
      return tile;
    }
    return (
      <Suspense fallback={tile}>
        <ResourcePdfThumb fileId={resourceId} thumbnail={null} onError={markFailed} />
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
export const ResourceCard = memo(function ResourceCard({
  resource,
  onOpen,
}: ResourceCardProps) {
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
});
