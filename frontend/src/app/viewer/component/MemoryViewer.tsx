import { Link } from "react-router-dom";

import { useReadMemory } from "../../generated-apis-types/memories/memories";
import type { MemorySchema } from "../../generated-apis-types/schemas";
import { formatDateTime } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { ViewerErrorState, ViewerLoading, ViewerMissing } from "./ViewerStates";
import { ViewerShell } from "./ViewerShell";
import { viewerErrorStatus } from "./viewer-utils";

function statusTone(status: MemorySchema["status"]): "moss" | "neutral" {
  return status === "active" ? "moss" : "neutral";
}

function LineageList({
  memories,
  empty,
}: {
  readonly memories: readonly MemorySchema[];
  readonly empty: string;
}) {
  if (memories.length === 0) {
    return <p className="viewer-memory__note">{empty}</p>;
  }
  return (
    <ul className="viewer-memory__links">
      {memories.map((memory) => (
        <li key={memory.memory_id}>
          <Link to={`/viewer/memory/${memory.memory_id}`}>
            <span>memory:{memory.memory_id}</span>
            <Badge tone={statusTone(memory.status)}>{memory.status}</Badge>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * The standalone memory viewer for `/viewer/memory/:memoryId`.
 *
 * It presents the memory as a pressed leaf, links its lineage within the
 * viewer, and hands the full trace (neighbours + complete chain) to the
 * existing `/memory/:memoryId` workspace.
 */
export function MemoryViewer({ memoryId }: { readonly memoryId: number }) {
  const query = useReadMemory(
    memoryId,
    { memory_range: 1, trace_history: true },
    { query: { retry: false } },
  );
  const status = viewerErrorStatus(query.error);

  if (query.isLoading) {
    return (
      <ViewerShell
        kind="Memory leaf"
        title={`Reading memory #${memoryId}`}
        backTo="/timeline"
        backLabel="Timeline"
      >
        <ViewerLoading label="Reading the pressed leaf" />
      </ViewerShell>
    );
  }

  if (query.error || !query.data) {
    return (
      <ViewerShell
        kind="Memory leaf"
        title={`Memory #${memoryId}`}
        backTo="/timeline"
        backLabel="Timeline"
      >
        {status === 404 ? (
          <ViewerMissing
            title="This memory is not in the archive."
            message={`memory:${memoryId} may have been removed or never saved. Deprecated memories normally remain readable.`}
            backTo="/timeline"
            backLabel="Back to the timeline"
          />
        ) : (
          <ViewerErrorState
            error={query.error}
            title="The memory could not be read"
            onRetry={() => void query.refetch()}
          />
        )}
      </ViewerShell>
    );
  }

  const memory = query.data.target;

  return (
    <ViewerShell
      kind="Memory leaf · pressed record"
      title={`Memory ${memory.memory_id}`}
      path={`memory:${memory.memory_id}`}
      backTo="/timeline"
      backLabel="Timeline"
      actions={
        <ButtonLink to={`/memory/${memory.memory_id}`} variant="secondary" size="sm">
          <Icon name="branch" size={15} />
          <span>Full memory trace</span>
        </ButtonLink>
      }
      meta={
        <>
          <Badge tone={statusTone(memory.status)} dot>
            {memory.status}
          </Badge>
          <Badge tone="neutral">{memory.source}</Badge>
          <span className="viewer-heading__date">
            <Icon name="clock" size={13} />
            <time dateTime={memory.update_time}>{formatDateTime(memory.update_time)}</time>
          </span>
        </>
      }
    >
      <div className="viewer-memory">
        <article className="viewer-memory__sheet">
          <header className="viewer-memory__head">
            <span className="viewer-memory__id">memory:{memory.memory_id}</span>
            <Badge tone={statusTone(memory.status)}>{memory.status}</Badge>
          </header>

          {memory.status === "deprecated" ? (
            <div className="viewer-notice viewer-notice--history" role="note">
              <Icon name="history" size={16} />
              <p>
                This memory is deprecated. It left search and the default timeline, but its
                record and lineage remain readable.
                {memory.superseded_by_id ? (
                  <>
                    {" "}
                    Read{" "}
                    <Link to={`/viewer/memory/${memory.superseded_by_id}`}>
                      memory:{memory.superseded_by_id}
                    </Link>
                    .
                  </>
                ) : null}
              </p>
            </div>
          ) : null}

          <blockquote className="viewer-memory__quote">{memory.content}</blockquote>

          <div className="viewer-memory__foot">
            <span>
              Created <time dateTime={memory.created_at}>{formatDateTime(memory.created_at)}</time>
            </span>
            <span>
              Updated <time dateTime={memory.update_time}>{formatDateTime(memory.update_time)}</time>
            </span>
          </div>
        </article>

        <aside className="viewer-memory__lineage" aria-label="Memory lineage">
          <section className="viewer-memory__section">
            <p className="eyebrow">This memory supersedes</p>
            <LineageList
              memories={query.data.supersedes}
              empty="No earlier memories are linked to this record."
            />
          </section>
          <section className="viewer-memory__section">
            <p className="eyebrow">Superseded by</p>
            {query.data.superseded_by ? (
              <LineageList
                memories={[query.data.superseded_by]}
                empty="Nothing has replaced this memory."
              />
            ) : (
              <p className="viewer-memory__note">
                Nothing has replaced this memory. It remains the current leaf.
              </p>
            )}
          </section>
          <section className="viewer-memory__section">
            <p className="eyebrow">Read with context</p>
            <p className="viewer-memory__note">
              The full trace shows temporal neighbours and the complete supersession chain.
            </p>
            <ButtonLink to={`/memory/${memory.memory_id}`} variant="secondary" size="sm">
              <Icon name="arrow-right" size={15} />
              Open trace
            </ButtonLink>
          </section>
        </aside>
      </div>
    </ViewerShell>
  );
}
