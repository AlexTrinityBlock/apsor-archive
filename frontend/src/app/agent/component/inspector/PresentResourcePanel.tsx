import { Icon } from "../../../component/Icon";
import {
  itemResourceTarget,
  safeResourceUrl,
  textField,
  viewerHref,
} from "../../trace";
import {
  InspectorFileStage,
  InspectorMemoryStage,
  LivePanel,
  PanelEmpty,
  PanelLink,
  type PanelProps,
} from "./common";

const RESOURCE_LABELS = {
  file: "File leaf",
  memory: "Memory leaf",
} as const;

const RESOURCE_ICONS = {
  file: "file",
  memory: "memory",
} as const;

/** `present_resource`: a presentation stage with the real viewer body. */
export function PresentResourcePanel({ item }: PanelProps) {
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Carrying the resource to the presentation stage." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="layers"
        title="The resource could not be presented"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  const target = itemResourceTarget(item);
  if (!target) {
    return (
      <PanelEmpty
        icon="layers"
        title="No resource on the stage"
        detail="This presentation result did not include a file or memory id."
      />
    );
  }
  const dataResource =
    item.data?.resource && typeof item.data.resource === "object"
      ? (item.data.resource as Record<string, unknown>)
      : null;
  const title =
    target.title ??
    textField(dataResource, "title") ??
    `${RESOURCE_LABELS[target.type]} #${target.id}`;
  const href = safeResourceUrl(dataResource?.viewer_url, target) ?? viewerHref(target);

  return (
    <div className="pi-presentation">
      <header className="pi-presentation__head">
        <span className="pi-presentation__mark" aria-hidden="true">
          <Icon name={RESOURCE_ICONS[target.type]} size={18} />
        </span>
        <div>
          <p className="eyebrow">Presentation stage</p>
          <strong>{title}</strong>
          <code>
            {RESOURCE_LABELS[target.type]} · #{target.id}
            {target.chunk !== null ? ` · chunk ${target.chunk}` : ""}
          </code>
        </div>
        <PanelLink to={href}>
          {target.type === "file" ? "Open in library" : "Open memory"}
        </PanelLink>
      </header>

      <div className="pi-presentation__stage">
        {target.type === "file" ? (
          <InspectorFileStage fileId={target.id} chunk={target.chunk} />
        ) : null}
        {target.type === "memory" ? (
          <InspectorMemoryStage memoryId={target.id} />
        ) : null}
      </div>
    </div>
  );
}
