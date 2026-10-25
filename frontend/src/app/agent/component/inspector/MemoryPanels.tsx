import { Link } from "react-router-dom";

import { CopyButton } from "../../../component/CopyButton";
import { Icon } from "../../../component/Icon";
import { useReadMemory } from "../../../generated-apis-types/memories/memories";
import type { MemorySchema } from "../../../generated-apis-types/schemas";
import { useI18n } from "../../../i18n";
import { truncate } from "../../../../lib/format";
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
  const { t, formatDateTime, formatNumber } = useI18n();
  const memoryId =
    memoryIdOf(item.data, item.arguments) ??
    (item.resource?.resourceType === "memory" ? item.resource.resourceId : null);
  const query = useReadMemory(
    memoryId ?? 0,
    { memory_range: 2, trace_history: true },
    { query: { enabled: memoryId !== null, retry: false } },
  );

  if (item.live || item.status.toLowerCase() === "running") {
    return (
      <LivePanel item={item} detail={t("chat.panels.memory.readingMemory")} />
    );
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="leaf"
        title={t("chat.panels.memory.readError")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
      />
    );
  }
  if (memoryId === null) {
    return (
      <PanelEmpty
        icon="leaf"
        title={t("chat.panels.memory.noMemoryIdTitle")}
        detail={t("chat.panels.memory.noMemoryIdDetail")}
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
          <p className="eyebrow">{t("chat.panels.memory.lineage")}</p>
          <strong>memory:{target.memory_id}</strong>
          <span>
            {target.status} ·{" "}
            {t("chat.panels.common.updated", {
              time: formatDateTime(target.update_time),
            })}
          </span>
        </div>
        <div className="pi-leaf-chain__head-actions">
          <CopyButton
            value={target.content}
            label={t("chat.panels.memory.copyMemory")}
            iconOnly
            title={t("chat.panels.memory.copyMemoryTitle")}
          />
          <PanelLink to={`/memory/${target.memory_id}`}>
            {t("chat.panels.common.fullTrace")}
          </PanelLink>
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
          <LeafRef
            key={`before-${memory.memory_id}`}
            memory={memory}
            role={t("chat.panels.memory.roleEarlier")}
          />
        ))}
        <LeafRef
          memory={target}
          role={t("chat.panels.memory.roleCurrent")}
        />
        {read.neighbors_after.map((memory) => (
          <LeafRef
            key={`after-${memory.memory_id}`}
            memory={memory}
            role={t("chat.panels.memory.roleLater")}
          />
        ))}
      </ul>

      <LineageSection
        label={t("chat.panels.memory.supersedes")}
        memories={read.supersedes}
      />
      {read.superseded_by ? (
        <LineageSection
          label={t("chat.panels.memory.supersededBy")}
          memories={[read.superseded_by]}
        />
      ) : null}

      {neighborIds.length > 0 ? (
        <p className="pi-leaf-chain__note">
          {t("chat.panels.memory.neighbours", {
            count: formatNumber(neighborIds.length),
          })}
        </p>
      ) : null}
    </div>
  );
}

/** `save_memory`: a wax-seal receipt for an appended memory. */
export function SaveMemoryPanel({ item }: PanelProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
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
    return (
      <LivePanel item={item} detail={t("chat.panels.memory.savingMemory")} />
    );
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="leaf"
        title={
          deprecating
            ? t("chat.panels.memory.deprecateError")
            : t("chat.panels.memory.saveError")
        }
        detail={item.detail ?? t("chat.panels.common.noStructured")}
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
          <p className="eyebrow">{t("chat.panels.memory.ledgerEyebrow")}</p>
          <h3>
            {t(
              deprecated.length === 1
                ? "chat.panels.memory.deprecatedOne"
                : "chat.panels.memory.deprecatedOther",
              { count: formatNumber(deprecated.length) },
            )}
          </h3>
          <blockquote>{t("chat.panels.memory.noReplacement")}</blockquote>
          <ul className="pi-seal-receipt__list">
            {deprecated.map((memory) => {
              const id = numberField(memory, "memory_id");
              const title = textField(memory, "title");
              return (
                <li key={id ?? title ?? "deprecated"}>
                  {id !== null ? (
                    <Link to={`/memory/${id}`}>
                      {t("chat.panels.memory.crystalId", { id })}
                    </Link>
                  ) : (
                    <span>{t("chat.panels.memory.crystal")}</span>
                  )}
                  <span>{title ?? t("chat.panels.memory.untitled")}</span>
                </li>
              );
            })}
          </ul>
          <dl className="pi-seal-receipt__meta">
            <div>
              <dt>{t("chat.panels.memory.status")}</dt>
              <dd>deprecated</dd>
            </div>
            <div>
              <dt>{t("chat.panels.memory.reason")}</dt>
              <dd>{reason ?? t("chat.panels.memory.notSupplied")}</dd>
            </div>
            <div>
              <dt>{t("chat.panels.memory.recorded")}</dt>
              <dd>
                {item.createdAt
                  ? formatDateTime(item.createdAt)
                  : t("chat.panels.memory.thisTurn")}
              </dd>
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
    t("chat.panels.memory.noContent");
  const status = saved?.status ?? textField(receipt, "status") ?? "saved";

  return (
    <div className="pi-seal-receipt">
      <div className="pi-seal-receipt__seal" aria-hidden="true">
        <span className="pi-seal-receipt__wax">
          <Icon name="leaf" size={20} />
        </span>
      </div>
      <div className="pi-seal-receipt__body">
        <p className="eyebrow">{t("chat.panels.memory.receiptEyebrow")}</p>
        <h3>
          {memoryId === null
            ? t("chat.panels.memory.newLeaf")
            : `memory:${memoryId}`}
        </h3>
        <blockquote>{content}</blockquote>
        <dl className="pi-seal-receipt__meta">
          <div>
            <dt>{t("chat.panels.memory.status")}</dt>
            <dd>{status}</dd>
          </div>
          <div>
            <dt>{t("chat.panels.memory.supersedesLabel")}</dt>
            <dd>
              {supersedes.length > 0
                ? supersedes.join(", ")
                : t("chat.panels.memory.nothing")}
            </dd>
          </div>
          <div>
            <dt>{t("chat.panels.memory.recorded")}</dt>
            <dd>
              {saved
                ? formatDateTime(saved.update_time)
                : t("chat.panels.memory.thisTurn")}
            </dd>
          </div>
        </dl>
        {memoryId !== null ? (
          <PanelLink to={`/memory/${memoryId}`}>
            {t("chat.panels.memory.openLeaf")}
          </PanelLink>
        ) : null}
      </div>
    </div>
  );
}
