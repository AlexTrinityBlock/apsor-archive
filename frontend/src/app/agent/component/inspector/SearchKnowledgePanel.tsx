import type { ReactNode } from "react";

import { Icon } from "../../../component/Icon";
import { basename, formatNumber, truncate } from "../../../../lib/format";
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

function fileResults(data: Record<string, unknown> | null): ResultTarget[] {
  return recordList(data?.file_results).map((record) => {
    const id = recordId(record, "file_id");
    const chunk = numberField(record, "chunk");
    const path =
      textField(record, "raw_file_path") ??
      textField(record, "path") ??
      `file ${id ?? "?"}`;
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

function memoryResults(data: Record<string, unknown> | null): ResultTarget[] {
  return recordList(data?.memory_results).map((record) => {
    const id = recordId(record, "memory_id");
    return {
      record,
      id,
      chunk: null,
      title: id === null ? "memory" : `memory:${id}`,
      detail: textField(record, "path"),
      excerpt: excerptOf(record, ["excerpt", "content"]),
      score: numberField(record, "score"),
      target: targetOf("memory", id, null, "memory"),
    };
  });
}

function summaryResults(data: Record<string, unknown> | null): ResultTarget[] {
  return recordList(data?.summary_results).map((record) => {
    const id = recordId(record, "memory_summary_id");
    const start = textField(record, "start") ?? textField(record, "period_start");
    const end = textField(record, "end") ?? textField(record, "period_end");
    return {
      record,
      id,
      chunk: null,
      title: id === null ? "summary" : `summary:${id}`,
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
  results,
}: {
  readonly kind: string;
  readonly label: string;
  readonly results: readonly ResultTarget[];
}) {
  return (
    <section className="pi-constellation__group" data-kind={kind}>
      <header className="pi-constellation__group-head">
        <span className="pi-constellation__orbit" aria-hidden="true">
          <span />
        </span>
        <span>{label}</span>
        <span className="pi-constellation__count">{results.length}</span>
      </header>
      {results.length === 0 ? (
        <p className="pi-constellation__quiet">No {label.toLowerCase()} in this pass.</p>
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
                    No inline excerpt was recorded for this result.
                  </p>
                )}
                {href ? <PanelLink to={href}>View result</PanelLink> : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ConstellationBody({ item }: PanelProps): ReactNode {
  const data = item.data;
  if (!data) {
    return (
      <PanelEmpty
        icon="search"
        title="No structured search preview"
        detail="The search ran, but this result has no UI preview payload. The recorded query and arguments remain below."
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
        <span>{textField(data, "query") ?? textField(item.arguments, "query") ?? "search"}</span>
        {numberField(data, "result_number") !== null ? (
          <span className="pi-constellation__limit">
            top {formatNumber(numberField(data, "result_number") ?? 0)} each
          </span>
        ) : null}
      </p>
      <ResultGroup kind="file" label="File leaves" results={fileResults(data)} />
      <ResultGroup kind="memory" label="Memory leaves" results={memoryResults(data)} />
      <ResultGroup kind="summary" label="Season summaries" results={summaryResults(data)} />
    </div>
  );
}

/** `search_knowledge`: a three-layer result constellation with excerpts. */
export function SearchKnowledgePanel({ item }: PanelProps) {
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Searching files, memories, and summaries." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="search"
        title="The search did not return"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }
  return <ConstellationBody item={item} />;
}

/** A compact excerpt preview used by the timeline and path panels. */
export function traceExcerpt(item: TraceItem, keys: readonly string[]): string {
  return truncate(excerptOf(item.data, keys), 220);
}
