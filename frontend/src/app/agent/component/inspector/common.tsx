import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../../component/Icon";
import { Loader } from "../../../component/Loader";
import { useGetFile } from "../../../generated-apis-types/files/files";
import { useReadMemory } from "../../../generated-apis-types/memories/memories";
import { useI18n } from "../../../i18n";
import { FileRenderer } from "../../../viewer/component/FileViewer";
import { viewerErrorMessage } from "../../../viewer/component/viewer-utils";
import type { TraceItem } from "../../trace";

export interface PanelProps {
  readonly item: TraceItem;
}

/** A quiet loading line that never shifts the inspector's frame. */
export function PanelLoading({ label }: { readonly label: string }) {
  return (
    <div className="pi-panel-state" role="status">
      <Loader size={17} label={label} />
      <span>{label}</span>
    </div>
  );
}

/** An empty or unavailable panel with a stable explanation. */
export function PanelEmpty({
  title,
  detail,
  icon = "info",
}: {
  readonly title: string;
  readonly detail: string;
  readonly icon?: IconName;
}) {
  return (
    <div className="pi-panel-empty">
      <span className="pi-panel-empty__mark" aria-hidden="true">
        <Icon name={icon} size={18} />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

/** A live tool call has no settled data yet; show the honest state instead. */
export function LivePanel({
  item,
  detail,
}: {
  readonly item: TraceItem;
  readonly detail?: string;
}) {
  const { t } = useI18n();
  return (
    <div className="pi-panel-live" aria-live="polite">
      <span className="pi-panel-live__pulse" aria-hidden="true" />
      <div>
        <strong>
          {t("chat.panels.common.liveReading", {
            tool: item.tool ?? t("chat.panels.common.toolFallback"),
          })}
        </strong>
        <p>{detail ?? t("chat.panels.common.liveDetail")}</p>
      </div>
    </div>
  );
}

export function PanelLink({
  to,
  children,
}: {
  readonly to: string;
  readonly children?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <Link className="pi-panel-link" to={to}>
      <span>{children ?? t("chat.panels.common.openInViewer")}</span>
      <Icon name="arrow-up-right" size={13} />
    </Link>
  );
}

export function PanelMeta({
  label,
  value,
}: {
  readonly label: string;
  readonly value: ReactNode;
}) {
  return (
    <div className="pi-panel-meta__row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** The actual file renderer, resolved from metadata, without ViewerShell. */
export function InspectorFileStage({
  fileId,
  chunk,
}: {
  readonly fileId: number;
  readonly chunk?: number | null;
}) {
  const { t } = useI18n();
  const query = useGetFile(fileId, { query: { retry: false } });

  if (query.isLoading) {
    return <PanelLoading label={t("chat.panels.common.fileReading")} />;
  }
  if (query.error || !query.data) {
    return (
      <PanelEmpty
        icon="layers"
        title={t("chat.panels.common.fileOpenError")}
        detail={viewerErrorMessage(query.error, t)}
      />
    );
  }

  const viewerPath = chunk
    ? `/library?tab=files&file=${fileId}&chunk=${chunk}`
    : `/library?tab=files&file=${fileId}`;

  return (
    <div className="pi-file-stage">
      <div className="pi-file-stage__head">
        <div>
          <p className="eyebrow">
            {chunk
              ? t("chat.panels.common.fileEmbeddedChunk")
              : t("chat.panels.common.fileEmbedded")}
          </p>
          <strong>{query.data.file_name}</strong>
          <code>{query.data.raw_file_path}</code>
        </div>
        <PanelLink to={viewerPath}>
          {t("chat.panels.common.openInLibrary")}
        </PanelLink>
      </div>
      <div className="pi-file-stage__body">
        <FileRenderer file={query.data} chunk={chunk ?? null} />
      </div>
    </div>
  );
}

/** A compact pressed-leaf stage for memory panels and preserved resources. */
export function InspectorMemoryStage({ memoryId }: { readonly memoryId: number }) {
  const { t, formatDateTime } = useI18n();
  const query = useReadMemory(
    memoryId,
    { memory_range: 1, trace_history: true },
    { query: { retry: false } },
  );

  if (query.isLoading) {
    return <PanelLoading label={t("chat.panels.common.memoryReading")} />;
  }
  if (query.error || !query.data) {
    return (
      <PanelEmpty
        icon="leaf"
        title={t("chat.panels.common.memoryOpenError")}
        detail={viewerErrorMessage(query.error, t)}
      />
    );
  }

  const memory = query.data.target;
  return (
    <div className="pi-memory-stage">
      <div className="pi-memory-stage__head">
        <span className="pi-memory-stage__id">memory:{memory.memory_id}</span>
        <span className="pi-memory-stage__status">{memory.status}</span>
      </div>
      <blockquote>{memory.content}</blockquote>
      <div className="pi-memory-stage__foot">
        <span>
          {t("chat.panels.common.updated", {
            time: formatDateTime(memory.update_time),
          })}
        </span>
        <PanelLink to={`/memory/${memory.memory_id}`}>
          {t("chat.panels.common.fullTrace")}
        </PanelLink>
      </div>
    </div>
  );
}
