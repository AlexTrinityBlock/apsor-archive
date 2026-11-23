import type { ReactNode } from "react";

import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { useI18n, type Translate } from "../../i18n";
import { formatArgumentValue } from "../format";
import { readPlotSpec } from "../plot";
import type { ResourceMeta, ToolResultMeta } from "../types";
import {
  buildToolPreview,
  type ToolPreview,
  type ToolPreviewCollection,
  type ToolPreviewExcerpt,
  type ToolPreviewField,
  type ToolPreviewHit,
} from "../tool-preview";
import { PlotBlock } from "./PlotBlock";
import { PlotSummary } from "./PlotSummary";
import { ResourceCard } from "./ResourceCard";
import { isToolFailure, toolStatusLabel, toolStatusTone } from "./status";

const VISIBLE_TEXT_LIMIT = 320;
const VISIBLE_ITEMS = 2;

interface ToolStepCardProps {
  readonly meta: ToolResultMeta;
  readonly step?: number | null;
  readonly entryId?: number | null;
  readonly callId?: string | null;
  readonly selected?: boolean;
  readonly onSelect?: (callId: string) => void;
  readonly onOpenResource?: (resource: ResourceMeta) => void;
}

function clipText(value: string, limit: number): string {
  const trimmed = value.trim();
  return trimmed.length > limit
    ? `${trimmed.slice(0, limit - 1).trimEnd()}…`
    : trimmed;
}

function externalHref(value: string | null): string | null {
  if (!value) {
    return null;
  }
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

function durationLabel(
  value: number | null,
  t: Translate,
  formatNumber: (value: number) => string,
): string | null {
  if (value === null) {
    return null;
  }
  if (value >= 1_000) {
    return t("chat.timeline.durationSeconds", {
      value: (value / 1_000).toFixed(2),
    });
  }
  return t("chat.timeline.durationMilliseconds", {
    value: formatNumber(value),
  });
}

function HitList({ hits }: { readonly hits: readonly ToolPreviewHit[] }) {
  const { t } = useI18n();
  return (
    <ul className="chat-tool-step__hits">
      {hits.map((hit, index) => {
        const href = externalHref(hit.url);
        return (
          <li className="chat-tool-step__hit" key={`${hit.url ?? "hit"}-${index}`}>
            <div className="chat-tool-step__hit-head">
              {href ? (
                <a href={href} target="_blank" rel="noreferrer noopener">
                  {hit.title ?? href}
                  <Icon name="external" size={11} />
                </a>
              ) : (
                <span>{hit.title ?? t("chat.timeline.untitledResult")}</span>
              )}
            </div>
            {hit.url ? (
              <code className="chat-tool-step__url" title={hit.url}>
                {hit.url}
              </code>
            ) : null}
            {hit.excerpt ? (
              <p className="chat-tool-step__excerpt">
                {clipText(hit.excerpt, 200)}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function SearchPreview({
  preview,
}: {
  readonly preview: Extract<ToolPreview, { kind: "search" }>;
}) {
  const { t, formatNumber } = useI18n();
  const visible = preview.hits.slice(0, VISIBLE_ITEMS);
  const rest = preview.hits.slice(VISIBLE_ITEMS);
  return (
    <section className="chat-tool-step__preview">
      <p className="chat-tool-step__preview-label">
        <span>
          {t(
            preview.total === 1
              ? "chat.timeline.searchResultsOne"
              : "chat.timeline.searchResultsOther",
            { count: formatNumber(preview.total) },
          )}
        </span>
        {preview.truncated ? (
          <span>{t("chat.timeline.truncated")}</span>
        ) : null}
      </p>
      <HitList hits={visible} />
      {rest.length > 0 ? (
        <details className="chat-tool-step__more">
          <summary>
            {t("chat.timeline.moreItems", {
              count: formatNumber(rest.length),
            })}
          </summary>
          <HitList hits={rest} />
        </details>
      ) : null}
    </section>
  );
}

function FetchPreview({
  preview,
}: {
  readonly preview: Extract<ToolPreview, { kind: "fetch" }>;
}) {
  const { t, formatNumber } = useI18n();
  let pageLabel: string | null = null;
  if (preview.page !== null) {
    pageLabel =
      preview.totalPages !== null
        ? t("chat.timeline.page", {
            page: formatNumber(preview.page),
            total: formatNumber(preview.totalPages),
          })
        : t("chat.timeline.pageOnly", {
            page: formatNumber(preview.page),
          });
  }
  const visible = clipText(preview.content, VISIBLE_TEXT_LIMIT);
  return (
    <section className="chat-tool-step__preview">
      <p className="chat-tool-step__preview-label">
        {preview.url ? (
          <code className="chat-tool-step__url" title={preview.url}>
            {preview.url}
          </code>
        ) : null}
        {pageLabel ? <span>{pageLabel}</span> : null}
        {preview.hasMore ? <span>{t("chat.timeline.hasMore")}</span> : null}
        {preview.contentChars !== null ? (
          <span>
            {t("chat.timeline.charCount", {
              count: formatNumber(preview.contentChars),
            })}
          </span>
        ) : null}
        {preview.truncated ? (
          <span>{t("chat.timeline.truncated")}</span>
        ) : null}
      </p>
      <p className="chat-tool-step__text">{visible}</p>
      {preview.content.length > visible.length ? (
        <details className="chat-tool-step__more">
          <summary>{t("chat.timeline.fullPreview")}</summary>
          <p className="chat-tool-step__text">{preview.content}</p>
        </details>
      ) : null}
    </section>
  );
}

function ExcerptList({
  items,
}: {
  readonly items: readonly ToolPreviewExcerpt[];
}) {
  return (
    <ul className="chat-tool-step__hits">
      {items.map((item, index) => (
        <li className="chat-tool-step__hit" key={`${item.label}-${index}`}>
          <div className="chat-tool-step__hit-head">
            <code className="chat-tool-step__hit-label">{item.label}</code>
            {item.title ? <span>{item.title}</span> : null}
          </div>
          <p className="chat-tool-step__excerpt">
            {clipText(item.excerpt, 220)}
          </p>
        </li>
      ))}
    </ul>
  );
}

function ExcerptsPreview({
  preview,
}: {
  readonly preview: Extract<ToolPreview, { kind: "excerpts" }>;
}) {
  const { t, formatNumber } = useI18n();
  const visible = preview.items.slice(0, VISIBLE_ITEMS);
  const rest = preview.items.slice(VISIBLE_ITEMS);
  return (
    <section className="chat-tool-step__preview">
      <p className="chat-tool-step__preview-label">
        {t(
          preview.total === 1
            ? "chat.timeline.matchOne"
            : "chat.timeline.matchOther",
          { count: formatNumber(preview.total) },
        )}
      </p>
      <ExcerptList items={visible} />
      {rest.length > 0 ? (
        <details className="chat-tool-step__more">
          <summary>
            {t("chat.timeline.moreItems", {
              count: formatNumber(rest.length),
            })}
          </summary>
          <ExcerptList items={rest} />
        </details>
      ) : null}
    </section>
  );
}

function TextPreview({
  preview,
}: {
  readonly preview: Extract<ToolPreview, { kind: "text" }>;
}) {
  const { t } = useI18n();
  const visible = clipText(preview.text, VISIBLE_TEXT_LIMIT);
  return (
    <section className="chat-tool-step__preview">
      <p className="chat-tool-step__preview-label">
        {preview.title ?? t("chat.timeline.resultPreview")}
      </p>
      <p className="chat-tool-step__text">{visible}</p>
      {preview.text.length > visible.length ? (
        <details className="chat-tool-step__more">
          <summary>{t("chat.timeline.fullPreview")}</summary>
          <p className="chat-tool-step__text">{preview.text}</p>
        </details>
      ) : null}
    </section>
  );
}

function CalculationPreview({
  preview,
}: {
  readonly preview: Extract<ToolPreview, { kind: "calculation" }>;
}) {
  const { t } = useI18n();
  return (
    <section className="chat-tool-step__preview">
      <p className="chat-tool-step__calculation">
        <code>{preview.expression}</code>
        <span>
          {t("chat.tool.calculationResult", { result: preview.formatted })}
        </span>
      </p>
    </section>
  );
}

function FieldList({
  fields,
}: {
  readonly fields: readonly ToolPreviewField[];
}) {
  return (
    <dl className="chat-tool-step__fields">
      {fields.map((field) => (
        <div key={field.key}>
          <dt>{field.key}</dt>
          <dd>{field.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function collectionCount(
  collection: ToolPreviewCollection,
  t: Translate,
  formatNumber: (value: number) => string,
): string {
  const singular =
    collection.unit === "fields"
      ? "chat.timeline.fieldCountOne"
      : "chat.timeline.itemCountOne";
  const plural =
    collection.unit === "fields"
      ? "chat.timeline.fieldCountOther"
      : "chat.timeline.itemCountOther";
  return t(collection.count === 1 ? singular : plural, {
    count: formatNumber(collection.count),
  });
}

function CollectionList({
  collections,
}: {
  readonly collections: readonly ToolPreviewCollection[];
}) {
  const { t, formatNumber } = useI18n();
  return (
    <p className="chat-tool-step__collections">
      {collections.map((collection) => {
        const count = collectionCount(collection, t, formatNumber);
        return (
          <span key={collection.key}>
            <code>{collection.key}</code>
            {collection.label ? <span>{collection.label}</span> : null}
            <span>{count}</span>
          </span>
        );
      })}
    </p>
  );
}

function FieldsPreview({
  preview,
}: {
  readonly preview: Extract<ToolPreview, { kind: "fields" }>;
}) {
  return (
    <section className="chat-tool-step__preview">
      {preview.fields.length > 0 ? (
        <FieldList fields={preview.fields} />
      ) : null}
      {preview.collections.length > 0 ? (
        <CollectionList collections={preview.collections} />
      ) : null}
    </section>
  );
}

function ToolPreviewBody({
  preview,
  running,
}: {
  readonly preview: ToolPreview;
  readonly running: boolean;
}) {
  const { t } = useI18n();
  switch (preview.kind) {
    case "search":
      return <SearchPreview preview={preview} />;
    case "fetch":
      return <FetchPreview preview={preview} />;
    case "excerpts":
      return <ExcerptsPreview preview={preview} />;
    case "text":
      return <TextPreview preview={preview} />;
    case "calculation":
      return <CalculationPreview preview={preview} />;
    case "fields":
      return <FieldsPreview preview={preview} />;
    default: {
      const note = running
        ? t("chat.tool.awaitingResult")
        : t("chat.tool.resultNote");
      return <p className="chat-result__note">{note}</p>;
    }
  }
}

/** One readable tool step shared by persisted history and the live stream. */
export function ToolStepCard({
  meta,
  step = null,
  entryId = null,
  callId = null,
  selected = false,
  onSelect,
  onOpenResource,
}: ToolStepCardProps) {
  const { t, formatNumber } = useI18n();
  const toolName = meta.tool ?? t("chat.tool.resultFallback");
  const failed = isToolFailure(meta.status);
  const running =
    meta.status?.toLowerCase() === "running" ||
    meta.status?.toLowerCase() === "pending";
  const duration = durationLabel(meta.durationMs, t, formatNumber);
  const hasPlot = readPlotSpec(meta.data) !== null;
  const preview: ToolPreview =
    hasPlot || meta.resource
      ? { kind: "none" }
      : buildToolPreview(meta.tool, meta.data);
  const argumentsList = meta.arguments ? Object.entries(meta.arguments) : [];
  const argumentPairs =
    meta.tool === "render_plot"
      ? []
      : argumentsList
          .filter(([, value]) => {
            return (
              typeof value === "string" ||
              typeof value === "number" ||
              typeof value === "boolean"
            );
          })
          .slice(0, 3)
          .map(([key, value]) => ({
            key,
            value: formatArgumentValue(value),
          }));

  let argumentsBody: ReactNode = null;
  if (meta.tool === "render_plot") {
    argumentsBody = (
      <PlotSummary arguments={meta.arguments} data={meta.data} />
    );
  } else if (argumentsList.length > 0) {
    argumentsBody = (
      <dl>
        {argumentsList.map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{formatArgumentValue(value)}</dd>
          </div>
        ))}
      </dl>
    );
  }

  const className = [
    "chat-result",
    "chat-tool-step",
    selected ? "is-active" : null,
    failed ? "is-error" : null,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article className={className} aria-busy={running || undefined}>
      <header className="chat-result__head chat-tool-step__head">
        <span className="chat-result__mark" aria-hidden="true">
          <Icon name="layers" size={15} />
        </span>
        <div className="chat-result__heading">
          <p className="eyebrow">{t("chat.timeline.toolStep")}</p>
          <h3>
            <code>{toolName}</code>
          </h3>
        </div>
        <span className="chat-tool-step__badges">
          <Badge tone={toolStatusTone(meta.status)}>
            {toolStatusLabel(meta.status, t, t("chat.common.recorded"))}
          </Badge>
          {duration ? (
            <span className="chat-tool-step__duration">{duration}</span>
          ) : null}
        </span>
        {callId && onSelect ? (
          <button
            type="button"
            className="chat-tool-step__inspect"
            onClick={() => onSelect(callId)}
            aria-pressed={selected}
            title={t("chat.tool.inspect")}
          >
            <Icon name="command" size={11} />
            {t("chat.timeline.inspect")}
          </button>
        ) : null}
      </header>

      <p className="chat-result__meta chat-tool-step__meta">
        {step !== null ? (
          <span>{t("chat.timeline.step", { step })}</span>
        ) : null}
        {entryId !== null ? (
          <span>{t("chat.tool.entry", { id: entryId })}</span>
        ) : null}
        {callId ? (
          <span className="chat-tool-step__call" title={callId}>
            {t("chat.timeline.callId", { id: callId })}
          </span>
        ) : null}
        {meta.errorCode ? (
          <span className="chat-result__error-code">
            {t("chat.timeline.errorCode", { code: meta.errorCode })}
          </span>
        ) : null}
      </p>

      {argumentPairs.length > 0 ? (
        <p className="chat-tool-step__args-line">
          <span className="chat-tool-step__args-label">
            {t("chat.timeline.arguments")}
          </span>
          {argumentPairs.map((pair) => (
            <span key={pair.key}>
              <code>{pair.key}</code>
              {pair.value}
            </span>
          ))}
        </p>
      ) : null}

      {meta.resource ? (
        <ResourceCard resource={meta.resource} onOpen={onOpenResource} />
      ) : null}

      {hasPlot ? <PlotBlock data={meta.data} /> : null}

      {!hasPlot && !meta.resource ? (
        <ToolPreviewBody preview={preview} running={running} />
      ) : null}

      {argumentsBody ? (
        <details className="chat-result__args">
          <summary>{t("chat.tool.argumentsUsed")}</summary>
          {argumentsBody}
        </details>
      ) : null}

      {failed && meta.detail ? (
        <div className="chat-tool-step__error-detail">
          <strong>{t("chat.timeline.errorDetail")}</strong>
          <p>{clipText(meta.detail, 800)}</p>
        </div>
      ) : null}
    </article>
  );
}
