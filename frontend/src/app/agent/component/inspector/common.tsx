import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../../component/Icon";
import { Loader } from "../../../component/Loader";
import { useGetFile } from "../../../generated-apis-types/files/files";
import { useReadMemory } from "../../../generated-apis-types/memories/memories";
import { formatDateTime } from "../../../../lib/format";
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
  detail = "The result preview will settle when the tool returns.",
}: {
  readonly item: TraceItem;
  readonly detail?: string;
}) {
  return (
    <div className="pi-panel-live" aria-live="polite">
      <span className="pi-panel-live__pulse" aria-hidden="true" />
      <div>
        <strong>{item.tool ?? "Tool"} · reading</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

export function PanelLink({
  to,
  children = "Open in viewer",
}: {
  readonly to: string;
  readonly children?: ReactNode;
}) {
  return (
    <Link className="pi-panel-link" to={to}>
      <span>{children}</span>
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
  const query = useGetFile(fileId, { query: { retry: false } });

  if (query.isLoading) {
    return <PanelLoading label="Reading the file leaf" />;
  }
  if (query.error || !query.data) {
    return (
      <PanelEmpty
        icon="layers"
        title="The file could not be opened"
        detail={viewerErrorMessage(query.error)}
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
            {chunk ? "File leaf · embedded at chunk" : "File leaf · embedded"}
          </p>
          <strong>{query.data.file_name}</strong>
          <code>{query.data.raw_file_path}</code>
        </div>
        <PanelLink to={viewerPath}>Open in library</PanelLink>
      </div>
      <div className="pi-file-stage__body">
        <FileRenderer file={query.data} chunk={chunk ?? null} />
      </div>
    </div>
  );
}

/** A compact pressed-leaf stage for memory panels and preserved resources. */
export function InspectorMemoryStage({ memoryId }: { readonly memoryId: number }) {
  const query = useReadMemory(
    memoryId,
    { memory_range: 1, trace_history: true },
    { query: { retry: false } },
  );

  if (query.isLoading) {
    return <PanelLoading label="Reading the pressed leaf" />;
  }
  if (query.error || !query.data) {
    return (
      <PanelEmpty
        icon="leaf"
        title="The memory could not be opened"
        detail={viewerErrorMessage(query.error)}
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
        <span>updated {formatDateTime(memory.update_time)}</span>
        <PanelLink to={`/memory/${memory.memory_id}`}>Full trace</PanelLink>
      </div>
    </div>
  );
}
