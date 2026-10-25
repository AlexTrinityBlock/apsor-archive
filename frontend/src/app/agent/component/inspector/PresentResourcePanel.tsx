import { Icon } from "../../../component/Icon";
import { useI18n } from "../../../i18n";
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

const RESOURCE_LABEL_KEYS = {
  file: "chat.panels.present.fileLeaf",
  memory: "chat.panels.present.memoryLeaf",
} as const;

const RESOURCE_ICONS = {
  file: "file",
  memory: "memory",
} as const;

/** `present_resource`: a presentation stage with the real viewer body. */
export function PresentResourcePanel({ item }: PanelProps) {
  const { t } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return (
      <LivePanel item={item} detail={t("chat.panels.present.liveDetail")} />
    );
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="layers"
        title={t("chat.panels.present.errorTitle")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
      />
    );
  }

  const target = itemResourceTarget(item);
  if (!target) {
    return (
      <PanelEmpty
        icon="layers"
        title={t("chat.panels.present.emptyTitle")}
        detail={t("chat.panels.present.emptyDetail")}
      />
    );
  }
  const dataResource =
    item.data?.resource && typeof item.data.resource === "object"
      ? (item.data.resource as Record<string, unknown>)
      : null;
  const resourceLabel = t(RESOURCE_LABEL_KEYS[target.type]);
  const title =
    target.title ??
    textField(dataResource, "title") ??
    `${resourceLabel} #${target.id}`;
  const href = safeResourceUrl(dataResource?.viewer_url, target) ?? viewerHref(target);

  return (
    <div className="pi-presentation">
      <header className="pi-presentation__head">
        <span className="pi-presentation__mark" aria-hidden="true">
          <Icon name={RESOURCE_ICONS[target.type]} size={18} />
        </span>
        <div>
          <p className="eyebrow">{t("chat.panels.present.stage")}</p>
          <strong>{title}</strong>
          <code>
            {resourceLabel} · #{target.id}
            {target.chunk !== null
              ? ` · ${t("chat.common.chunk", { chunk: target.chunk })}`
              : ""}
          </code>
        </div>
        <PanelLink to={href}>
          {target.type === "file"
            ? t("chat.panels.common.openInLibrary")
            : t("chat.panels.memory.openLeaf")}
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
