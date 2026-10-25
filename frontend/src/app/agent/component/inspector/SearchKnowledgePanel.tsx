import type { ReactNode } from "react";

import { Icon } from "../../../component/Icon";
import { useI18n, type Translate } from "../../../i18n";
import { basename, truncate } from "../../../../lib/format";
import {
  excerptOf,
  numberField,
  recordId,
  recordList,
  safeResourceUrl,
  textField,
  type ResourceTarget,
  type TraceItem,
} from "../../trace";
import { LivePanel, PanelEmpty, PanelLink, type PanelProps } from "./common";

interface ResultTarget {
  readonly record: Record<string, unknown>;
  readonly id: number | null;
  readonly chunk: number | null;
  readonly title: string;
  readonly detail: string | null;
  readonly excerpt: string;
  readonly score: number | null;
  readonly target: ResourceTarget | null;
}

function targetOf(
  type: ResourceTarget["type"],
  id: number | null,
  chunk: number | null,
  title: string,
): ResourceTarget | null {
  return id === null ? null : { type, id, chunk, title };
}

function fileResults(
  data: Record<string, unknown> | null,
  t: Translate,
): ResultTarget[] {
  return recordList(data?.file_results).map((record) => {
    const id = recordId(record, "file_id");
    const chunk = numberField(record, "chunk");
    const path =
      textField(record, "raw_file_path") ??
      textField(record, "path") ??
      `${t("chat.resource.file")} ${id ?? "?"}`;
    return {
      record,
      id,
      chunk,
      title: basename(path),
      detail: path,
      excerpt: excerptOf(record, ["excerpt", "content"]),
      score: numberField(record, "score"),
      target: targetOf("file", id, chunk, basename(path)),
    };
  });
}

function memoryResults(
  data: Record<string, unknown> | null,
  t: Translate,
): ResultTarget[] {
  return recordList(data?.memory_results).map((record) => {
    const id = recordId(record, "memory_id");
    return {
      record,
      id,
      chunk: null,
      title:
        id === null ? t("chat.resource.memory") : `memory:${id}`,
      detail: textField(record, "path"),
      excerpt: excerptOf(record, ["excerpt", "content"]),
      score: numberField(record, "score"),
      target: targetOf("memory", id, null, t("chat.resource.memory")),
    };
  });
}

function summaryResults(
  data: Record<string, unknown> | null,
  t: Translate,
): ResultTarget[] {
  return recordList(data?.summary_results).map((record) => {
    const id = recordId(record, "memory_summary_id");
    const start = textField(record, "start") ?? textField(record, "period_start");
    const end = textField(record, "end") ?? textField(record, "period_end");
    return {
      record,
      id,
      chunk: null,
      title:
        id === null
          ? t("chat.panels.search.summaryFallback")
          : `summary:${id}`,
      detail: start && end ? `${start} → ${end}` : start,
      excerpt: excerptOf(record, ["excerpt", "content"]),
      score: numberField(record, "score"),
      target: null,
    };
  });
}

function resultKey(kind: string, result: ResultTarget, index: number): string {
  const identity = result.id === null ? `title:${result.title}` : String(result.id);
  const chunk = result.chunk === null ? "no-chunk" : `chunk-${result.chunk}`;
  return `${kind}-${identity}-${chunk}-${index}`;
}

function ResultGroup({
  kind,
  label,
  empty,
  results,
}: {
  readonly kind: string;
  readonly label: string;
  readonly empty: string;
  readonly results: readonly ResultTarget[];
}) {
  const { t, formatNumber } = useI18n();
  return (
    <section className="pi-constellation__group" data-kind={kind}>
      <header className="pi-constellation__group-head">
        <span className="pi-constellation__orbit" aria-hidden="true">
          <span />
        </span>
        <span>{label}</span>
        <span className="pi-constellation__count">
          {formatNumber(results.length)}
        </span>
      </header>
      {results.length === 0 ? (
        <p className="pi-constellation__quiet">{empty}</p>
      ) : (
        <ul className="pi-constellation__list">
          {results.map((result, index) => {
            const href = safeResourceUrl(result.record.viewer_url, result.target);
            return (
              <li className="pi-constellation__node" key={resultKey(kind, result, index)}>
                <div className="pi-constellation__node-head">
                  <strong>{result.title}</strong>
                  {result.score !== null ? (
                    <span className="pi-constellation__score">
                      {result.score.toFixed(3)}
                    </span>
                  ) : null}
                </div>
                {result.detail ? <code>{result.detail}</code> : null}
                {result.excerpt ? (
                  <p className="pi-constellation__excerpt">{result.excerpt}</p>
                ) : (
                  <p className="pi-constellation__excerpt is-muted">
                    {t("chat.panels.search.noExcerpt")}
                  </p>
                )}
                {href ? (
                  <PanelLink to={href}>
                    {t("chat.panels.search.viewResult")}
                  </PanelLink>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ConstellationBody({ item }: PanelProps): ReactNode {
  const { t, formatNumber } = useI18n();
  const data = item.data;
  if (!data) {
    return (
      <PanelEmpty
        icon="search"
        title={t("chat.panels.search.noPreviewTitle")}
        detail={t("chat.panels.search.noPreviewDetail")}
      />
    );
  }
  return (
    <div className="pi-constellation">
      <div className="pi-constellation__sky" aria-hidden="true">
        <span className="pi-constellation__ring" />
        <span className="pi-constellation__ring pi-constellation__ring--inner" />
        <span className="pi-constellation__core" />
      </div>
      <p className="pi-constellation__query">
        <Icon name="search" size={13} />
        <span>
          {textField(data, "query") ??
            textField(item.arguments, "query") ??
            t("chat.panels.search.queryFallback")}
        </span>
        {numberField(data, "result_number") !== null ? (
          <span className="pi-constellation__limit">
            {t("chat.panels.search.topEach", {
              count: formatNumber(numberField(data, "result_number") ?? 0),
            })}
          </span>
        ) : null}
      </p>
      <ResultGroup
        kind="file"
        label={t("chat.panels.search.fileLeaves")}
        empty={t("chat.panels.search.fileEmpty")}
        results={fileResults(data, t)}
      />
      <ResultGroup
        kind="memory"
        label={t("chat.panels.search.memoryLeaves")}
        empty={t("chat.panels.search.memoryEmpty")}
        results={memoryResults(data, t)}
      />
      <ResultGroup
        kind="summary"
        label={t("chat.panels.search.seasonSummaries")}
        empty={t("chat.panels.search.summaryEmpty")}
        results={summaryResults(data, t)}
      />
    </div>
  );
}

/** `search_knowledge`: a three-layer result constellation with excerpts. */
export function SearchKnowledgePanel({ item }: PanelProps) {
  const { t } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return (
      <LivePanel item={item} detail={t("chat.panels.search.liveDetail")} />
    );
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="search"
        title={t("chat.panels.search.errorTitle")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
      />
    );
  }
  return <ConstellationBody item={item} />;
}

/** A compact excerpt preview used by the timeline and path panels. */
export function traceExcerpt(item: TraceItem, keys: readonly string[]): string {
  return truncate(excerptOf(item.data, keys), 220);
}
