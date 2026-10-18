import { Link, useLocation } from "react-router-dom";

import type {
  MemoryReadSchema,
  MemorySchema,
} from "../../generated-apis-types/schemas";
import type { BadgeTone } from "../../type/ui";

import { ApiError } from "../../../apis/fetch-client";
import { Badge } from "../../component/Badge";
import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";
import { QueryState } from "../../component/QueryState";
import { useReadMemory } from "../../generated-apis-types/memories/memories";
import { formatDate, formatDateTime, formatNumber, truncate } from "../../../lib/format";

import { MemoryMissing } from "./MemoryMissing";
import {
  parseMemorySaveReceipt,
  type MemorySaveReceipt,
} from "./helpers";

interface MemoryReadViewProps {
  readonly memoryId: number;
}

function statusTone(status: MemorySchema["status"]): BadgeTone {
  return status === "active" ? "moss" : "neutral";
}

function MemoryLinkCard({
  memory,
  compact = false,
}: {
  readonly memory: MemorySchema;
  readonly compact?: boolean;
}) {
  return (
    <Link
      className={["memory-link-card", compact ? "is-compact" : null].filter(Boolean).join(" ")}
      to={`/memory/${memory.memory_id}`}
    >
      <span className="memory-link-card__head">
        <span className="memory-link-card__id">memory:{memory.memory_id}</span>
        <Badge tone={statusTone(memory.status)}>{memory.status}</Badge>
      </span>
      <time className="memory-link-card__time" dateTime={memory.update_time}>
        {formatDateTime(memory.update_time)}
      </time>
      <p className="memory-link-card__copy">
        {truncate(memory.content, compact ? 112 : 150)}
      </p>
    </Link>
  );
}

function SaveReceipt({ receipt }: { readonly receipt: MemorySaveReceipt }) {
  const count = receipt.deprecated.length;
  let copy = "No earlier memory was deprecated by this save. The new record is active.";
  if (count > 0) {
    const noun = count === 1 ? "memory was" : "memories were";
    copy = `${count} earlier ${noun} marked deprecated. The records remain readable and stay in the supersession chain.`;
  }
  return (
    <Panel
      tone="moss"
      eyebrow="Just pressed"
      title="Memory saved"
      className="memory-receipt reveal reveal-2"
    >
      <p className="memory-receipt__copy">{copy}</p>
      {count > 0 ? (
        <ul className="memory-receipt__list">
          {receipt.deprecated.map((memory) => (
            <li key={memory.memory_id}>
              <MemoryLinkCard memory={memory} compact />
            </li>
          ))}
        </ul>
      ) : null}

      {receipt.summary ? (
        <div className="memory-receipt__summary">
          <header className="memory-receipt__summary-head">
            <div>
              <p className="eyebrow">Auto-created summary</p>
              <strong>summary:{receipt.summary.memory_summary_id}</strong>
            </div>
            <Badge tone={receipt.summary.generator === "deepseek" ? "moss" : "ochre"} dot>
              {receipt.summary.generator}
            </Badge>
          </header>
          <p className="memory-receipt__summary-content">{receipt.summary.content}</p>
          <dl className="memory-receipt__summary-meta">
            <div>
              <dt>Model</dt>
              <dd>
                <code>{receipt.summary.model ?? "not reported"}</code>
              </dd>
            </div>
            <div>
              <dt>Memories</dt>
              <dd>{formatNumber(receipt.summary.memory_count)}</dd>
            </div>
            <div>
              <dt>Period</dt>
              <dd>
                {formatDate(receipt.summary.period_start)} {"\u2013"}{" "}
                {formatDate(receipt.summary.period_end)}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
    </Panel>
  );
}

function Chain({ data }: { readonly data: MemoryReadSchema }) {
  return (
    <Panel
      eyebrow="Trace history"
      title="Supersession chain"
      className="memory-chain-panel reveal reveal-4"
    >
      {data.chain.length <= 1 ? (
        <p className="memory-note">
          No supersession links are recorded for this memory. It stands alone in the chain.
        </p>
      ) : (
        <>
          <ol className="memory-chain">
            {data.chain.map((memory, index) => (
              <li className="memory-chain__step" key={memory.memory_id}>
                {index > 0 ? (
                  <span className="memory-chain__arrow" aria-hidden="true">
                    <Icon name="arrow-down" size={14} />
                  </span>
                ) : null}
                <Link
                  className={[
                    "memory-chain__node",
                    memory.status === "active" ? "is-active" : "is-deprecated",
                    memory.memory_id === data.target.memory_id ? "is-target" : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  to={`/memory/${memory.memory_id}`}
                  aria-current={memory.memory_id === data.target.memory_id ? "page" : undefined}
                >
                  <span className="memory-chain__node-head">
                    <span>memory:{memory.memory_id}</span>
                    <Badge tone={statusTone(memory.status)}>{memory.status}</Badge>
                  </span>
                  <time dateTime={memory.update_time}>{formatDateTime(memory.update_time)}</time>
                  <span className="memory-chain__excerpt">{truncate(memory.content, 88)}</span>
                </Link>
              </li>
            ))}
          </ol>
          <p className="memory-chain__note">
            Oldest at the top. Each step moves toward the current memory, including deprecated
            leaves.
          </p>
        </>
      )}
    </Panel>
  );
}

function Lineage({ data }: { readonly data: MemoryReadSchema }) {
  return (
    <Panel
      eyebrow="Direct lineage"
      title="What this memory replaces"
      className="memory-lineage-panel reveal reveal-3"
    >
      <div className="memory-lineage">
        <section className="memory-lineage__column">
          <h3 className="memory-subhead">This memory supersedes</h3>
          {data.supersedes.length > 0 ? (
            <ul className="memory-link-list">
              {data.supersedes.map((memory) => (
                <li key={memory.memory_id}>
                  <MemoryLinkCard memory={memory} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="memory-note">No earlier memories are listed on this record.</p>
          )}
        </section>
        <section className="memory-lineage__column">
          <h3 className="memory-subhead">Superseded by</h3>
          {data.superseded_by ? (
            <MemoryLinkCard memory={data.superseded_by} />
          ) : (
            <p className="memory-note">
              Nothing has replaced this memory. It remains the current leaf in its chain.
            </p>
          )}
        </section>
      </div>
    </Panel>
  );
}

function Neighbours({ data }: { readonly data: MemoryReadSchema }) {
  return (
    <Panel
      eyebrow="Adjacent in time"
      title="Neighbouring memories"
      className="memory-neighbours-panel reveal reveal-3"
      action={<Badge tone="neutral">memory_range = 1</Badge>}
    >
      <div className="memory-neighbours">
        <section className="memory-neighbours__column">
          <h3 className="memory-subhead">Before</h3>
          {data.neighbors_before.length > 0 ? (
            <ul className="memory-link-list">
              {data.neighbors_before.map((memory) => (
                <li key={memory.memory_id}>
                  <MemoryLinkCard memory={memory} compact />
                </li>
              ))}
            </ul>
          ) : (
            <p className="memory-note">This is the earliest memory in the archive.</p>
          )}
        </section>
        <section className="memory-neighbours__column">
          <h3 className="memory-subhead">After</h3>
          {data.neighbors_after.length > 0 ? (
            <ul className="memory-link-list">
              {data.neighbors_after.map((memory) => (
                <li key={memory.memory_id}>
                  <MemoryLinkCard memory={memory} compact />
                </li>
              ))}
            </ul>
          ) : (
            <p className="memory-note">This is the latest memory in the archive.</p>
          )}
        </section>
      </div>
    </Panel>
  );
}

function SupersedeAction({ target }: { readonly target: MemorySchema }) {
  if (target.status !== "active") {
    return (
      <Button
        variant="secondary"
        size="sm"
        disabled
        title="This memory is already deprecated."
      >
        <Icon name="branch" size={15} />
        Supersede this memory
      </Button>
    );
  }
  return (
    <ButtonLink
      to={`/memory/new?supersedes=${target.memory_id}`}
      variant="primary"
      size="sm"
    >
      <Icon name="branch" size={15} />
      Supersede this memory
    </ButtonLink>
  );
}

function MemoryRecord({ target }: { readonly target: MemorySchema }) {
  return (
    <article className="memory-record reveal reveal-2">
      <header className="memory-record__head">
        <span className="memory-record__id">memory:{target.memory_id}</span>
        <Badge tone={statusTone(target.status)} dot>
          {target.status}
        </Badge>
      </header>

      {target.status === "deprecated" ? (
        <div className="memory-record__deprecated" role="note">
          <Icon name="history" size={17} />
          <p>
            This memory is deprecated. It left search and the default timeline, but remains
            readable here.{" "}
            {target.superseded_by_id ? (
              <Link to={`/memory/${target.superseded_by_id}`}>
                Read successor memory:{target.superseded_by_id}
              </Link>
            ) : null}
          </p>
        </div>
      ) : null}

      <blockquote className="memory-record__content">{target.content}</blockquote>

      <dl className="memory-record__meta">
        <div>
          <dt>Update time</dt>
          <dd>
            <time dateTime={target.update_time}>{formatDateTime(target.update_time)}</time>
          </dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>
            <Badge tone="neutral">{target.source}</Badge>
          </dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatDateTime(target.created_at)}</dd>
        </div>
        <div className="memory-record__meta-wide">
          <dt>Supersedes ids</dt>
          <dd>
            {target.supersedes_ids.length > 0 ? (
              <span className="memory-record__ids">
                {target.supersedes_ids.map((id) => (
                  <Link key={id} to={`/memory/${id}`}>
                    memory:{id}
                  </Link>
                ))}
              </span>
            ) : (
              <span className="memory-record__none">None recorded</span>
            )}
          </dd>
        </div>
      </dl>
    </article>
  );
}

function MemoryBody({
  data,
  receipt,
}: {
  readonly data: MemoryReadSchema;
  readonly receipt: MemorySaveReceipt | null;
}) {
  return (
    <div className="memory-detail">
      <main className="memory-detail__main">
        {receipt ? <SaveReceipt receipt={receipt} /> : null}
        <MemoryRecord target={data.target} />
        <Lineage data={data} />
        <Neighbours data={data} />
      </main>
      <aside className="memory-detail__side">
        <Chain data={data} />
        <Panel
          tone="plain"
          eyebrow="Traceability"
          title="Why deprecated stays visible"
          className="memory-trace-note"
        >
          <p>
            Supersession is a lineage action, not a delete. The old memory leaves search and the
            default timeline, while its chunks disappear from retrieval and its record keeps a
            pointer to the successor.
          </p>
          <p>
            This page reads the target with <code>memory_range=1</code> and{" "}
            <code>trace_history=true</code>, so both temporal neighbours and the full chain are
            available in one pass.
          </p>
        </Panel>
      </aside>
    </div>
  );
}

/** Single-memory trace with lineage, neighbours, and a save receipt when present. */
export function MemoryReadView({ memoryId }: MemoryReadViewProps) {
  const location = useLocation();
  const receipt = parseMemorySaveReceipt(location.state);
  const query = useReadMemory(
    memoryId,
    { memory_range: 1, trace_history: true },
    { query: { retry: false } },
  );

  if (query.error instanceof ApiError && query.error.status === 404) {
    return <MemoryMissing memoryId={String(memoryId)} />;
  }

  const target = query.data?.target;

  return (
    <div className="page memory-page">
      <PageHeader
        eyebrow="Memory · trace"
        title={`Memory ${memoryId}`}
        description="One pressed leaf, read with its direct replacements, its temporal neighbours, and the full supersession chain. Deprecated memories remain legible; only their search presence is withdrawn."
        meta={
          target ? (
            <Badge tone={statusTone(target.status)} dot>
              {target.status}
            </Badge>
          ) : (
            <span>read_memory · trace_history=true</span>
          )
        }
        actions={
          <div className="memory-actions">
            {target ? <SupersedeAction target={target} /> : null}
            <ButtonLink to="/timeline" variant="ghost" size="sm">
              <Icon name="arrow-right" size={15} className="memory-back-icon" />
              Back to timeline
            </ButtonLink>
          </div>
        }
      />

      <QueryState loading={query.isPending} error={query.error} loadingLabel="Reading the memory trace">
        {query.data ? <MemoryBody data={query.data} receipt={receipt} /> : null}
      </QueryState>
    </div>
  );
}
