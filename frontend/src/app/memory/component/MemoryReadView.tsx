import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import type {
  MemoryReadSchema,
  MemorySchema,
} from "../../generated-apis-types/schemas";

import { ApiError } from "../../../apis/fetch-client";
import { Badge } from "../../component/Badge";
import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";
import { useReadMemory } from "../../generated-apis-types/memories/memories";
import { formatDate, formatDateTime, formatNumber, truncate } from "../../../lib/format";

import {
  MemoryDeprecateDialog,
  MemoryEditDialog,
} from "./MemoryActionDialogs";
import { MemoryMissing } from "./MemoryMissing";
import { MemoryErrorState, MemorySkeleton } from "./MemoryStates";
import { MemoryStatus } from "./MemoryStatus";
import {
  parseMemorySaveReceipt,
  type MemorySaveReceipt,
} from "./helpers";

interface MemoryReadViewProps {
  readonly memoryId: number;
}

function MemoryMiniCard({ memory }: { readonly memory: MemorySchema }) {
  return (
    <Link
      className={[
        "memory-mini",
        memory.status === "active" ? "is-active" : "is-deprecated",
      ].join(" ")}
      to={`/memory/${memory.memory_id}`}
    >
      <span className="memory-mini__head">
        <span className="memory-mini__id">CRYSTAL #{memory.memory_id}</span>
        <MemoryStatus status={memory.status} small />
      </span>
      <time className="memory-mini__time" dateTime={memory.update_time}>
        {formatDateTime(memory.update_time)}
      </time>
      <span className="memory-mini__copy">{truncate(memory.title, 124)}</span>
    </Link>
  );
}

function MiniList({ memories }: { readonly memories: readonly MemorySchema[] }) {
  return (
    <div className="memory-mini-list">
      {memories.map((memory) => (
        <MemoryMiniCard key={memory.memory_id} memory={memory} />
      ))}
    </div>
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
      tone="plain"
      eyebrow="Just pressed"
      title="Memory saved"
      className="memory-receipt"
    >
      <p className="memory-receipt__copy">{copy}</p>
      {count > 0 ? (
        <div className="memory-receipt__list">
          <MiniList memories={receipt.deprecated} />
        </div>
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
                <span className="code-inline">{receipt.summary.model ?? "not reported"}</span>
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

function MemoryRecord({ target }: { readonly target: MemorySchema }) {
  return (
    <article className="memory-record">
      <header className="memory-record__head">
        <span className="memory-record__id">CRYSTAL #{target.memory_id}</span>
        <MemoryStatus status={target.status} />
      </header>

      <h2 className="memory-record__title">{target.title}</h2>

      {target.status === "deprecated" ? (
        <div className="memory-record__deprecated" role="note">
          <Icon name="history" size={17} />
          <p>
            This memory is deprecated. It left default search and the timeline, but remains
            readable here.{" "}
            {target.superseded_by_id ? (
              <Link to={`/memory/${target.superseded_by_id}`}>
                Read successor CRYSTAL #{target.superseded_by_id}
              </Link>
            ) : (
              "It was retired directly; no successor replaced it."
            )}
          </p>
          {target.deprecated_reason ? (
            <p className="memory-record__reason">
              Reason: {target.deprecated_reason}
            </p>
          ) : null}
        </div>
      ) : null}

      <blockquote className="memory-record__content">{target.content}</blockquote>

      {/* The API exposes occurrence time as update_time; created_at is press time. */}
      <dl className="meta-grid memory-record__meta">
        <div className="meta-item">
          <dt className="meta-key">Occurred</dt>
          <dd className="meta-value">
            <time dateTime={target.update_time}>{formatDateTime(target.update_time)}</time>
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Pressed</dt>
          <dd className="meta-value">
            <time dateTime={target.created_at}>{formatDateTime(target.created_at)}</time>
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Source</dt>
          <dd className="meta-value">{target.source}</dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">Record id</dt>
          <dd className="meta-value">memory:{target.memory_id}</dd>
        </div>
      </dl>
    </article>
  );
}

function Lineage({ data }: { readonly data: MemoryReadSchema }) {
  return (
    <Panel
      eyebrow="Direct lineage"
      title="What this memory replaces"
      className="memory-lineage-panel"
    >
      <div className="memory-lineage">
        <section className="memory-lineage__column">
          <h3 className="memory-subhead">This memory supersedes</h3>
          {data.supersedes.length > 0 ? (
            <MiniList memories={data.supersedes} />
          ) : (
            <p className="memory-note">No earlier memories are listed on this record.</p>
          )}
        </section>
        <section className="memory-lineage__column">
          <h3 className="memory-subhead">Superseded by</h3>
          {data.superseded_by ? (
            <MiniList memories={[data.superseded_by]} />
          ) : (
            <p className="memory-note">
              {data.target.status === "deprecated"
                ? "This memory was retired directly. No later record replaced it."
                : "Nothing has replaced this memory. It remains the current leaf in its chain."}
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
      eyebrow="Adjacent in occurrence order"
      title="Neighbouring memories"
      className="memory-neighbours-panel"
    >
      <div className="memory-neighbours">
        <section className="memory-neighbours__column">
          <h3 className="memory-subhead">Before</h3>
          {data.neighbors_before.length > 0 ? (
            <MiniList memories={data.neighbors_before} />
          ) : (
            <p className="memory-note">This is the earliest memory in the archive.</p>
          )}
        </section>
        <section className="memory-neighbours__column">
          <h3 className="memory-subhead">After</h3>
          {data.neighbors_after.length > 0 ? (
            <MiniList memories={data.neighbors_after} />
          ) : (
            <p className="memory-note">This is the latest memory in the archive.</p>
          )}
        </section>
      </div>
    </Panel>
  );
}

function Chain({ data }: { readonly data: MemoryReadSchema }) {
  return (
    <Panel
      eyebrow="Full chain"
      title="Supersession history"
      className="memory-chain-panel"
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
                  <span className="memory-chain__head">
                    <span>CRYSTAL #{memory.memory_id}</span>
                    <MemoryStatus status={memory.status} small />
                  </span>
                  <time className="memory-chain__time" dateTime={memory.update_time}>
                    {formatDateTime(memory.update_time)}
                  </time>
                  <span className="memory-chain__excerpt">{truncate(memory.content, 92)}</span>
                </Link>
              </li>
            ))}
          </ol>
          <p className="memory-chain__note">
            {data.chain.length >= 20
              ? "The API returns at most 20 linked records; this chain is at that cap."
              : "Oldest at the top. Each step moves toward the current memory, including deprecated leaves."}
          </p>
        </>
      )}
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

function ReadBody({
  data,
  receipt,
}: {
  readonly data: MemoryReadSchema;
  readonly receipt: MemorySaveReceipt | null;
}) {
  return (
    <div className="memory-reader__layout">
      <div className="memory-reader__main">
        {receipt ? <SaveReceipt receipt={receipt} /> : null}
        <MemoryRecord target={data.target} />
        <Lineage data={data} />
        <Neighbours data={data} />
      </div>
      <aside className="memory-reader__side">
        <Chain data={data} />
      </aside>
    </div>
  );
}

/** Single-memory reader with lineage, neighbours, and a save receipt when present. */
export function MemoryReadView({ memoryId }: MemoryReadViewProps) {
  const location = useLocation();
  const receipt = parseMemorySaveReceipt(location.state);
  const query = useReadMemory(
    memoryId,
    { memory_range: 1, trace_history: true },
    { query: { retry: false } },
  );
  const [editOpen, setEditOpen] = useState(false);
  const [deprecateOpen, setDeprecateOpen] = useState(false);

  if (query.error instanceof ApiError && query.error.status === 404) {
    return <MemoryMissing memoryId={String(memoryId)} />;
  }

  const target = query.data?.target;

  return (
    <div className="content-container memory-page memory-reader-page">
      <nav className="memory-breadcrumb" aria-label="Breadcrumb">
        <Link to="/memory">Memory Vault</Link>
        <span aria-hidden="true">/</span>
        <span className="memory-breadcrumb__current" aria-current="page">
          CRYSTAL #{memoryId}
        </span>
      </nav>

      <PageHeader
        eyebrow="Memory · reader"
        title={`CRYSTAL #${memoryId}`}
        description="One pressed memory with its direct lineage, its temporal neighbours, and the full supersession chain. Deprecated crystals remain readable after they leave search and the timeline."
        meta={
          target ? (
            <MemoryStatus status={target.status} small />
          ) : (
            <span className="memory-page-header__meta">Reading record</span>
          )
        }
        actions={
          <div className="memory-actions">
            {target ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setEditOpen(true)}
              >
                <Icon name="pencil" size={14} />
                Edit text
              </Button>
            ) : null}
            {target?.status === "active" ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDeprecateOpen(true)}
              >
                <Icon name="history" size={14} />
                Deprecate
              </Button>
            ) : null}
            {target ? <SupersedeAction target={target} /> : null}
            <ButtonLink to="/memory" variant="ghost" size="sm">
              <Icon name="arrow-right" size={15} className="memory-back-icon" />
              Back to vault
            </ButtonLink>
          </div>
        }
      />

      {query.isPending ? <MemorySkeleton label="Reading the memory trace" count={2} /> : null}
      {query.isError ? (
        <MemoryErrorState
          title="The memory trace did not answer."
          description="The record could not be read. Retry, or return to the vault and choose another crystal."
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : null}
      {query.data ? <ReadBody data={query.data} receipt={receipt} /> : null}

      {target && editOpen ? (
        <MemoryEditDialog
          memory={target}
          onClose={() => setEditOpen(false)}
        />
      ) : null}
      {target && deprecateOpen ? (
        <MemoryDeprecateDialog
          memory={target}
          onClose={() => setDeprecateOpen(false)}
        />
      ) : null}
    </div>
  );
}
