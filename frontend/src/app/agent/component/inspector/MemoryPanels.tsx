import { Link } from "react-router-dom";

import { CopyButton } from "../../../component/CopyButton";
import { Icon } from "../../../component/Icon";
import { useReadMemory } from "../../../generated-apis-types/memories/memories";
import type { MemorySchema } from "../../../generated-apis-types/schemas";
import { formatDateTime, truncate } from "../../../../lib/format";
import { numberField, recordId, textField } from "../../trace";
import {
  InspectorMemoryStage,
  LivePanel,
  PanelEmpty,
  PanelLink,
  type PanelProps,
} from "./common";

function idsOf(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const ids: number[] = [];
  for (const item of value) {
    if (typeof item === "number" && Number.isSafeInteger(item) && item > 0) {
      ids.push(item);
    } else if (typeof item === "object" && item !== null) {
      const id = recordId(item as Record<string, unknown>, "memory_id");
      if (id !== null) {
        ids.push(id);
      }
    }
  }
  return ids;
}

function memoryIdOf(
  data: Record<string, unknown> | null,
  args: Record<string, unknown> | null,
): number | null {
  return recordId(data, "memory_id") ?? recordId(args, "memory_id", "id");
}

function LeafRef({
  memory,
  role,
}: {
  readonly memory: Pick<MemorySchema, "memory_id" | "content" | "status">;
  readonly role: string;
}) {
  return (
    <li className="pi-leaf-chain__leaf" data-role={role}>
      <span className="pi-leaf-chain__vein" aria-hidden="true" />
      <div>
        <span className="pi-leaf-chain__role">{role}</span>
        <p>{truncate(memory.content, 260)}</p>
        <div className="pi-leaf-chain__meta">
          <Link to={`/memory/${memory.memory_id}`}>
            memory:{memory.memory_id}
          </Link>
          <span>{memory.status}</span>
        </div>
      </div>
    </li>
  );
}

function LineageSection({
  label,
  memories,
}: {
  readonly label: string;
  readonly memories: readonly MemorySchema[];
}) {
  if (memories.length === 0) {
    return null;
  }
  return (
    <section className="pi-leaf-chain__section">
      <p className="eyebrow">{label}</p>
      <ul>
        {memories.map((memory) => (
          <li key={memory.memory_id}>
            <Link to={`/memory/${memory.memory_id}`}>memory:{memory.memory_id}</Link>
            <span>{truncate(memory.content, 140)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** `read_memory`: a pressed-leaf lineage around one central record. */
export function ReadMemoryPanel({ item }: PanelProps) {
  const memoryId =
    memoryIdOf(item.data, item.arguments) ??
    (item.resource?.resourceType === "memory" ? item.resource.resourceId : null);
  const query = useReadMemory(
    memoryId ?? 0,
    { memory_range: 2, trace_history: true },
    { query: { enabled: memoryId !== null, retry: false } },
  );

  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Reading the memory and its neighbours." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="leaf"
        title="The pressed leaf could not be read"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }
  if (memoryId === null) {
    return (
      <PanelEmpty
        icon="leaf"
        title="No memory id in this result"
        detail="The inspector received no target memory to open."
      />
    );
  }
  if (query.isLoading) {
    return <InspectorMemoryStage memoryId={memoryId} />;
  }
  if (query.error || !query.data) {
    return <InspectorMemoryStage memoryId={memoryId} />;
  }

  const read = query.data;
  const target = read.target;
  const data = item.data;
  const neighborIds = [...idsOf(data?.neighbors_before), ...idsOf(data?.neighbors_after)];

  return (
    <div className="pi-leaf-chain">
      <header className="pi-leaf-chain__head">
        <div>
          <p className="eyebrow">Pressed-leaf lineage</p>
          <strong>memory:{target.memory_id}</strong>
          <span>{target.status} · updated {formatDateTime(target.update_time)}</span>
        </div>
        <div className="pi-leaf-chain__head-actions">
          <CopyButton
            value={target.content}
            label="Copy memory"
            iconOnly
            title="Copy the memory text"
          />
          <PanelLink to={`/memory/${target.memory_id}`}>Full trace</PanelLink>
        </div>
      </header>

      <div className="pi-leaf-chain__target">
        <span className="pi-leaf-chain__specimen" aria-hidden="true">
          <Icon name="leaf" size={18} />
        </span>
        <blockquote>{target.content}</blockquote>
      </div>

      <ul className="pi-leaf-chain__leaves">
        {read.neighbors_before.map((memory) => (
          <LeafRef key={`before-${memory.memory_id}`} memory={memory} role="earlier" />
        ))}
        <LeafRef memory={target} role="current leaf" />
        {read.neighbors_after.map((memory) => (
          <LeafRef key={`after-${memory.memory_id}`} memory={memory} role="later" />
        ))}
      </ul>

      <LineageSection label="This memory supersedes" memories={read.supersedes} />
      {read.superseded_by ? (
        <LineageSection label="Superseded by" memories={[read.superseded_by]} />
      ) : null}

      {neighborIds.length > 0 ? (
        <p className="pi-leaf-chain__note">
          Neighbour range recorded: {neighborIds.length} adjacent memories. The
          full trace keeps the complete chain.
        </p>
      ) : null}
    </div>
  );
}

/** `save_memory`: a wax-seal receipt for an appended memory. */
export function SaveMemoryPanel({ item }: PanelProps) {
  const data = item.data;
  const deprecating = data?.mode === "deprecate";
  const receipt = (data?.memory ?? null) as Record<string, unknown> | null;
  const memoryId =
    numberField(receipt, "memory_id") ??
    recordId(data, "memory_id") ??
    recordId(item.arguments, "memory_id");
  const query = useReadMemory(
    memoryId ?? 0,
    { memory_range: 0, trace_history: true },
    { query: { enabled: memoryId !== null, retry: false } },
  );

  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Pressing the confirmed memory leaf." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="leaf"
        title={deprecating ? "The memories were not deprecated" : "The memory was not saved"}
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  if (deprecating) {
    const deprecated = Array.isArray(data?.deprecated)
      ? (data.deprecated as Record<string, unknown>[])
      : [];
    const reason = textField(data, "reason");
    return (
      <div className="pi-seal-receipt">
        <div className="pi-seal-receipt__seal" aria-hidden="true">
          <span className="pi-seal-receipt__wax">
            <Icon name="history" size={20} />
          </span>
        </div>
        <div className="pi-seal-receipt__body">
          <p className="eyebrow">Ledger update · memory retired</p>
          <h3>
            {deprecated.length === 1
              ? "1 memory deprecated"
              : `${deprecated.length} memories deprecated`}
          </h3>
          <blockquote>
            No replacement memory was written. The records stay readable in the
            vault.
          </blockquote>
          <ul className="pi-seal-receipt__list">
            {deprecated.map((memory) => {
              const id = numberField(memory, "memory_id");
              const title = textField(memory, "title");
              return (
                <li key={id ?? title ?? "deprecated"}>
                  {id !== null ? (
                    <Link to={`/memory/${id}`}>CRYSTAL #{id}</Link>
                  ) : (
                    <span>CRYSTAL</span>
                  )}
                  <span>{title ?? "Untitled memory"}</span>
                </li>
              );
            })}
          </ul>
          <dl className="pi-seal-receipt__meta">
            <div>
              <dt>Status</dt>
              <dd>deprecated</dd>
            </div>
            <div>
              <dt>Reason</dt>
              <dd>{reason ?? "not supplied"}</dd>
            </div>
            <div>
              <dt>Recorded</dt>
              <dd>{item.createdAt ? formatDateTime(item.createdAt) : "this turn"}</dd>
            </div>
          </dl>
        </div>
      </div>
    );
  }

  const saved = query.data?.target;
  const supersedes = idsOf(data?.supersedes);
  const content =
    textField(receipt, "content") ??
    saved?.content ??
    textField(item.arguments, "content") ??
    "No memory text was recorded in the receipt.";
  const status = saved?.status ?? textField(receipt, "status") ?? "saved";

  return (
    <div className="pi-seal-receipt">
      <div className="pi-seal-receipt__seal" aria-hidden="true">
        <span className="pi-seal-receipt__wax">
          <Icon name="leaf" size={20} />
        </span>
      </div>
      <div className="pi-seal-receipt__body">
        <p className="eyebrow">Wax-seal receipt · memory appended</p>
        <h3>{memoryId === null ? "New memory leaf" : `memory:${memoryId}`}</h3>
        <blockquote>{content}</blockquote>
        <dl className="pi-seal-receipt__meta">
          <div>
            <dt>Status</dt>
            <dd>{status}</dd>
          </div>
          <div>
            <dt>Supersedes</dt>
            <dd>{supersedes.length > 0 ? supersedes.join(", ") : "nothing"}</dd>
          </div>
          <div>
            <dt>Recorded</dt>
            <dd>{saved ? formatDateTime(saved.update_time) : "this turn"}</dd>
          </div>
        </dl>
        {memoryId !== null ? (
          <PanelLink to={`/memory/${memoryId}`}>Open the pressed leaf</PanelLink>
        ) : null}
      </div>
    </div>
  );
}
