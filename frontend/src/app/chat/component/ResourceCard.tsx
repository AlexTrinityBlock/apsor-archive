import { ButtonLink } from "../../component/Button";
import { Icon, type IconName } from "../../component/Icon";
import { basename } from "../../../lib/format";
import type { ResourceMeta } from "../types";

const RESOURCE_ICONS: Record<ResourceMeta["resourceType"], IconName> = {
  file: "file",
  media: "ring",
  memory: "memory",
};

const RESOURCE_LABELS: Record<ResourceMeta["resourceType"], string> = {
  file: "File",
  media: "Media",
  memory: "Memory",
};

/** A structured `present_resource` card; only validated viewer paths link out. */
export function ResourceCard({ resource }: { readonly resource: ResourceMeta }) {
  const title =
    resource.title ??
    `${RESOURCE_LABELS[resource.resourceType]} ${
      resource.resourceId === null ? "" : `#${resource.resourceId}`
    }`.trim();
  const details = [
    RESOURCE_LABELS[resource.resourceType],
    resource.mimeType,
    resource.chunk === null ? null : `chunk ${resource.chunk}`,
    resource.rawFilePath ? basename(resource.rawFilePath) : null,
  ].filter((item): item is string => item !== null && item.length > 0);

  return (
    <article className="chat-resource">
      <span className="chat-resource__icon" aria-hidden="true">
        <Icon name={RESOURCE_ICONS[resource.resourceType]} size={20} />
      </span>
      <div className="chat-resource__body">
        <p className="eyebrow">Presented {RESOURCE_LABELS[resource.resourceType]}</p>
        <h3>{title}</h3>
        <p className="chat-resource__meta">{details.join(" · ")}</p>
      </div>
      {resource.viewerUrl ? (
        <ButtonLink
          to={resource.viewerUrl}
          variant="secondary"
          size="sm"
          className="chat-resource__action"
        >
          Open in viewer
          <Icon name="arrow-up-right" size={14} />
        </ButtonLink>
      ) : (
        <span className="chat-resource__unavailable">Viewer link unavailable</span>
      )}
    </article>
  );
}
