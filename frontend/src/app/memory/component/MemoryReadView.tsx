import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import type {
  MemoryReadSchema,
  MemorySchema,
} from "../../generated-apis-types/schemas";

import { ApiError } from "../../../apis/fetch-client";
import { Badge } from "../../component/Badge";
import { Button, ButtonLink } from "../../component/Button";
import { CopyButton } from "../../component/CopyButton";
import { Icon } from "../../component/Icon";
import { PageHeader } from "../../component/PageHeader";
import { Panel } from "../../component/Panel";
import { useReadMemory } from "../../generated-apis-types/memories/memories";
import { useI18n } from "../../i18n";
import { truncate } from "../../../lib/format";

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
  const { t, formatDateTime } = useI18n();

  return (
    <Link
      className={[
        "memory-mini",
        memory.status === "active" ? "is-active" : "is-deprecated",
      ].join(" ")}
      to={`/memory/${memory.memory_id}`}
    >
      <span className="memory-mini__head">
        <span className="memory-mini__id">
          {t("memory.common.crystal", { id: memory.memory_id })}
        </span>
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
  const { t, formatDate, formatNumber } = useI18n();
  const count = receipt.deprecated.length;
  let copy = t("memory.reader.saveReceipt.noDeprecated");
  if (count === 1) {
    copy = t("memory.reader.saveReceipt.deprecatedOne");
  } else if (count > 1) {
    copy = t("memory.reader.saveReceipt.deprecatedOther", {
      count: formatNumber(count),
    });
  }

  return (
    <Panel
      tone="plain"
      eyebrow={t("memory.reader.saveReceipt.eyebrow")}
      title={t("memory.reader.saveReceipt.title")}
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
              <p className="eyebrow">
                {t("memory.reader.saveReceipt.autoSummary")}
              </p>
              <strong>summary:{receipt.summary.memory_summary_id}</strong>
            </div>
            <Badge tone={receipt.summary.generator === "deepseek" ? "moss" : "ochre"} dot>
              {receipt.summary.generator}
            </Badge>
          </header>
          <p className="memory-receipt__summary-content">{receipt.summary.content}</p>
          <dl className="memory-receipt__summary-meta">
            <div>
              <dt>{t("memory.reader.saveReceipt.model")}</dt>
              <dd>
                <span className="code-inline">
                  {receipt.summary.model ?? t("memory.common.notReported")}
                </span>
              </dd>
            </div>
            <div>
              <dt>{t("memory.reader.saveReceipt.memories")}</dt>
              <dd>{formatNumber(receipt.summary.memory_count)}</dd>
            </div>
            <div>
              <dt>{t("memory.reader.saveReceipt.period")}</dt>
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
  const { t, formatDateTime } = useI18n();

  return (
    <article className="memory-record">
      <header className="memory-record__head">
        <span className="memory-record__id">
          {t("memory.common.crystal", { id: target.memory_id })}
        </span>
        <MemoryStatus status={target.status} />
      </header>

      <h2 className="memory-record__title">{target.title}</h2>

      {target.status === "deprecated" ? (
        <div className="memory-record__deprecated" role="note">
          <Icon name="history" size={17} />
          <p>
            {t("memory.reader.record.deprecatedNote")}{" "}
            {target.superseded_by_id ? (
              <Link to={`/memory/${target.superseded_by_id}`}>
                {t("memory.reader.record.readSuccessor", {
                  id: target.superseded_by_id,
                })}
              </Link>
            ) : (
              t("memory.reader.record.retiredDirectly")
            )}
          </p>
          {target.deprecated_reason ? (
            <p className="memory-record__reason">
              {t("memory.common.reason", {
                reason: target.deprecated_reason,
              })}
            </p>
          ) : null}
        </div>
      ) : null}

      <blockquote className="memory-record__content">{target.content}</blockquote>

      {/* The API exposes occurrence time as update_time; created_at is press time. */}
      <dl className="meta-grid memory-record__meta">
        <div className="meta-item">
          <dt className="meta-key">{t("memory.common.occurred")}</dt>
          <dd className="meta-value">
            <time dateTime={target.update_time}>{formatDateTime(target.update_time)}</time>
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("memory.common.pressed")}</dt>
          <dd className="meta-value">
            <time dateTime={target.created_at}>{formatDateTime(target.created_at)}</time>
          </dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("memory.common.source")}</dt>
          <dd className="meta-value">{target.source}</dd>
        </div>
        <div className="meta-item">
          <dt className="meta-key">{t("memory.common.recordId")}</dt>
          <dd className="meta-value">memory:{target.memory_id}</dd>
        </div>
      </dl>
    </article>
  );
}

function Lineage({ data }: { readonly data: MemoryReadSchema }) {
  const { t } = useI18n();

  return (
    <Panel
      eyebrow={t("memory.reader.lineage.eyebrow")}
      title={t("memory.reader.lineage.title")}
      className="memory-lineage-panel"
    >
      <div className="memory-lineage">
        <section className="memory-lineage__column">
          <h3 className="memory-subhead">
            {t("memory.reader.lineage.supersedesHeading")}
          </h3>
          {data.supersedes.length > 0 ? (
            <MiniList memories={data.supersedes} />
          ) : (
            <p className="memory-note">
              {t("memory.reader.lineage.supersedesEmpty")}
            </p>
          )}
        </section>
        <section className="memory-lineage__column">
          <h3 className="memory-subhead">
            {t("memory.reader.lineage.supersededByHeading")}
          </h3>
          {data.superseded_by ? (
            <MiniList memories={[data.superseded_by]} />
          ) : (
            <p className="memory-note">
              {data.target.status === "deprecated"
                ? t("memory.reader.lineage.retiredEmpty")
                : t("memory.reader.lineage.currentEmpty")}
            </p>
          )}
        </section>
      </div>
    </Panel>
  );
}

function Neighbours({ data }: { readonly data: MemoryReadSchema }) {
  const { t } = useI18n();

  return (
    <Panel
      eyebrow={t("memory.reader.neighbours.eyebrow")}
      title={t("memory.reader.neighbours.title")}
      className="memory-neighbours-panel"
    >
      <div className="memory-neighbours">
        <section className="memory-neighbours__column">
          <h3 className="memory-subhead">
            {t("memory.reader.neighbours.before")}
          </h3>
          {data.neighbors_before.length > 0 ? (
            <MiniList memories={data.neighbors_before} />
          ) : (
            <p className="memory-note">
              {t("memory.reader.neighbours.earliest")}
            </p>
          )}
        </section>
        <section className="memory-neighbours__column">
          <h3 className="memory-subhead">
            {t("memory.reader.neighbours.after")}
          </h3>
          {data.neighbors_after.length > 0 ? (
            <MiniList memories={data.neighbors_after} />
          ) : (
            <p className="memory-note">
              {t("memory.reader.neighbours.latest")}
            </p>
          )}
        </section>
      </div>
    </Panel>
  );
}

function Chain({ data }: { readonly data: MemoryReadSchema }) {
  const { t, formatDateTime } = useI18n();

  return (
    <Panel
      eyebrow={t("memory.reader.chain.eyebrow")}
      title={t("memory.reader.chain.title")}
      className="memory-chain-panel"
    >
      {data.chain.length <= 1 ? (
        <p className="memory-note">{t("memory.reader.chain.empty")}</p>
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
                    <span>{t("memory.common.crystal", { id: memory.memory_id })}</span>
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
              ? t("memory.reader.chain.capped")
              : t("memory.reader.chain.order")}
          </p>
        </>
      )}
    </Panel>
  );
}

function SupersedeAction({ target }: { readonly target: MemorySchema }) {
  const { t } = useI18n();

  if (target.status !== "active") {
    return (
      <Button
        variant="secondary"
        size="sm"
        disabled
        title={t("memory.reader.supersede.disabledTitle")}
      >
        <Icon name="branch" size={15} />
        {t("memory.reader.supersede.action")}
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
      {t("memory.reader.supersede.action")}
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
  const { t } = useI18n();
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
      <nav className="memory-breadcrumb" aria-label={t("memory.common.breadcrumbAria")}>
        <Link to="/memory">{t("memory.vault.title")}</Link>
        <span aria-hidden="true">/</span>
        <span className="memory-breadcrumb__current" aria-current="page">
          {t("memory.common.crystal", { id: memoryId })}
        </span>
      </nav>

      <PageHeader
        eyebrow={t("memory.reader.eyebrow")}
        title={t("memory.common.crystal", { id: memoryId })}
        description={t("memory.reader.description")}
        meta={
          target ? (
            <MemoryStatus status={target.status} small />
          ) : (
            <span className="memory-page-header__meta">
              {t("memory.reader.readingRecord")}
            </span>
          )
        }
        actions={
          <div className="memory-actions">
            {target ? (
              <CopyButton
                value={target.content}
                label={t("memory.common.copyMemory")}
                title={t("memory.common.copyMemoryTitle")}
              />
            ) : null}
            {target ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setEditOpen(true)}
              >
                <Icon name="pencil" size={14} />
                {t("memory.reader.editText")}
              </Button>
            ) : null}
            {target?.status === "active" ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setDeprecateOpen(true)}
              >
                <Icon name="history" size={14} />
                {t("memory.reader.deprecate")}
              </Button>
            ) : null}
            {target ? <SupersedeAction target={target} /> : null}
            <ButtonLink to="/memory" variant="ghost" size="sm">
              <Icon name="arrow-right" size={15} className="memory-back-icon" />
              {t("memory.reader.backToVault")}
            </ButtonLink>
          </div>
        }
      />

      {query.isPending ? (
        <MemorySkeleton label={t("memory.reader.skeleton")} count={2} />
      ) : null}
      {query.isError ? (
        <MemoryErrorState
          title={t("memory.reader.errorTitle")}
          description={t("memory.reader.errorDescription")}
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
