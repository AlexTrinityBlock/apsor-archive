import type { ReactNode } from "react";

import { Button, ButtonLink } from "../../component/Button";
import { Icon, type IconName } from "../../component/Icon";
import { useI18n } from "../../i18n";
import { basename } from "../../../lib/format";
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

interface ResourceCardProps {
  readonly resource: ResourceMeta;
  /** When present, the card opens the in-situ preview instead of navigating. */
  readonly onOpen?: (resource: ResourceMeta) => void;
}

/** A structured `present_resource` card with a real file or memory target. */
export function ResourceCard({ resource, onOpen }: ResourceCardProps) {
  const { t } = useI18n();
  const resourceLabel = t(RESOURCE_LABEL_KEYS[resource.resourceType]);
  const title =
    resource.title ??
    `${resourceLabel} ${
      resource.resourceId === null ? "" : `#${resource.resourceId}`
    }`.trim();
  const details = [
    resourceLabel,
    resource.mimeType,
    resource.chunk === null
      ? null
      : t("chat.common.chunk", { chunk: resource.chunk }),
    resource.rawFilePath ? basename(resource.rawFilePath) : null,
  ].filter((item): item is string => item !== null && item.length > 0);
  const href = resourceHref(resource);
  const fileAction = onOpen
    ? t("chat.resource.preview")
    : t("chat.resource.openFile");
  const actionLabel =
    resource.resourceType === "file"
      ? fileAction
      : t("chat.resource.openMemory");

  let action: ReactNode;
  if (onOpen) {
    action = (
      <Button
        variant="secondary"
        size="sm"
        className="chat-resource__action"
        onClick={() => onOpen(resource)}
      >
        {actionLabel}
        <Icon name="arrow-right" size={13} />
      </Button>
    );
  } else if (href) {
    action = (
      <ButtonLink
        to={href}
        variant="secondary"
        size="sm"
        className="chat-resource__action"
      >
        {actionLabel}
        <Icon name="arrow-up-right" size={13} />
      </ButtonLink>
    );
  } else {
    action = (
      <span className="chat-resource__unavailable">
        {t("chat.resource.noTarget")}
      </span>
    );
  }

  return (
    <article className="chat-resource">
      <span className="chat-resource__icon" aria-hidden="true">
        <Icon name={RESOURCE_ICONS[resource.resourceType]} size={18} />
      </span>
      <div className="chat-resource__body">
        <p className="mono-label">
          {t(PRESENTED_LABEL_KEYS[resource.resourceType])}
        </p>
        <h3>{title}</h3>
        <p className="chat-resource__meta">{details.join(" · ")}</p>
      </div>
      {action}
    </article>
  );
}
