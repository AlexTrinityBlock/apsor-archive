import { Badge } from "../../../component/Badge";
import { Icon } from "../../../component/Icon";
import { CopyButton } from "../../../component/CopyButton";
import { useI18n } from "../../../i18n";
import {
  numberField,
  recordList,
  textField,
} from "../../trace";
import { LivePanel, PanelEmpty, type PanelProps } from "./common";

interface WebSearchResult {
  readonly title: string;
  readonly url: string;
  readonly excerpt: string;
  readonly score: number | null;
}

function webResults(data: Record<string, unknown> | null): WebSearchResult[] {
  return recordList(data?.results).map((result) => ({
    title: textField(result, "title") ?? "",
    url: textField(result, "url") ?? "",
    excerpt: textField(result, "excerpt") ?? "",
    score: numberField(result, "score"),
  }));
}

/** `web_search`: the public results the model actually received. */
export function WebSearchPanel({ item }: PanelProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail={t("chat.panels.web.searchLive")} />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="search"
        title={t("chat.panels.web.searchErrorTitle")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
      />
    );
  }

  const data = item.data;
  const query = textField(data, "query") ?? textField(item.arguments, "query") ?? "";
  const provider =
    textField(data, "provider") ?? t("chat.panels.web.searchFallback");
  const retrievedAt = textField(data, "retrieved_at");
  const results = webResults(data);
  const cached = data?.cached === true;
  const truncated = data?.truncated === true || data?.tool_truncated === true;

  return (
    <div className="pi-web">
      <header className="pi-web__head">
        <div className="pi-web__heading">
          <p className="eyebrow">{t("chat.panels.web.searchHeading")}</p>
          <strong>{query || t("chat.panels.web.untitledQuery")}</strong>
          <code>
            {provider}
            {retrievedAt
              ? ` · ${t("chat.panels.web.retrieved", {
                  time: formatDateTime(retrievedAt),
                })}`
              : ""}
          </code>
        </div>
        <div className="pi-web__badges">
          {cached ? (
            <Badge tone="ochre">{t("chat.panels.web.cached")}</Badge>
          ) : null}
          {truncated ? (
            <Badge tone="neutral">{t("chat.panels.web.truncated")}</Badge>
          ) : null}
          <Badge tone={results.length > 0 ? "moss" : "neutral"}>
            {t(
              results.length === 1
                ? "chat.panels.web.resultsOne"
                : "chat.panels.web.resultsOther",
              { count: formatNumber(results.length) },
            )}
          </Badge>
        </div>
      </header>

      {results.length === 0 ? (
        <PanelEmpty
          icon="search"
          title={t("chat.panels.web.noResultsTitle")}
          detail={t("chat.panels.web.noResultsDetail")}
        />
      ) : (
        <ol className="pi-web-results">
          {results.map((result, index) => (
            <li className="pi-web-result" key={`${result.url}-${index}`}>
              <div className="pi-web-result__head">
                <span className="pi-web-result__index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <a
                  href={result.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  title={result.url}
                >
                  {result.title ||
                    result.url ||
                    t("chat.panels.web.untitledResult")}
                  <Icon name="external" size={12} />
                </a>
                {result.url ? (
                  <CopyButton
                    value={result.url}
                    label={t("chat.panels.web.copyUrl")}
                    iconOnly
                  />
                ) : null}
              </div>
              {result.url ? <code className="pi-web-result__url">{result.url}</code> : null}
              {result.excerpt ? (
                <p className="pi-web-result__excerpt">{result.excerpt}</p>
              ) : null}
              {result.score !== null ? (
                <span className="pi-web-result__score">
                  {t("chat.panels.web.score", {
                    score: result.score.toFixed(3),
                  })}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** `web_fetch`: the fetched page body and its source metadata. */
export function WebFetchPanel({ item }: PanelProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail={t("chat.panels.web.fetchLive")} />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="external"
        title={t("chat.panels.web.fetchErrorTitle")}
        detail={item.detail ?? t("chat.panels.common.noStructured")}
      />
    );
  }

  const data = item.data;
  const url =
    textField(data, "url") ?? textField(item.arguments, "url") ?? "";
  const provider =
    textField(data, "provider") ?? t("chat.panels.web.fetchFallback");
  const retrievedAt = textField(data, "retrieved_at");
  const content = textField(data, "content") ?? "";
  const chars = numberField(data, "content_chars");
  const page = numberField(data, "page");
  const totalPages = numberField(data, "total_pages");
  const offset = numberField(data, "offset");
  const returnedLines = numberField(data, "returned_lines");
  const totalLines = numberField(data, "total_lines");
  const lineEnd =
    offset !== null && returnedLines !== null && returnedLines > 0
      ? offset + returnedLines - 1
      : null;
  const pageLabel =
    page !== null &&
    totalPages !== null &&
    page > 0 &&
    totalPages > 0 &&
    page <= totalPages
      ? t("chat.panels.web.page", {
          page: formatNumber(page),
          total: formatNumber(totalPages),
        })
      : null;
  const lineLabel =
    offset !== null && totalLines !== null && lineEnd !== null
      ? t("chat.panels.web.lines", {
          start: formatNumber(offset),
          end: formatNumber(lineEnd),
          total: formatNumber(totalLines),
        })
      : null;
  const cached = data?.cached === true;
  const truncated = data?.truncated === true || data?.tool_truncated === true;
  const hasMore = data?.has_more === true;
  const sourceTruncated = data?.source_truncated === true;

  return (
    <div className="pi-web">
      <header className="pi-web__head">
        <div className="pi-web__heading">
          <p className="eyebrow">{t("chat.panels.web.fetchHeading")}</p>
          <a
            className="pi-web__url"
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            title={url}
          >
            {url || t("chat.panels.web.untitledUrl")}
            <Icon name="external" size={12} />
          </a>
          <code>
            {provider}
            {retrievedAt
              ? ` · ${t("chat.panels.web.retrieved", {
                  time: formatDateTime(retrievedAt),
                })}`
              : ""}
            {chars !== null
              ? ` · ${t("chat.panels.web.chars", {
                  count: formatNumber(chars),
                })}`
              : ""}
            {pageLabel ? ` · ${pageLabel}` : ""}
            {lineLabel ? ` · ${lineLabel}` : ""}
          </code>
        </div>
        <div className="pi-web__badges">
          {cached ? (
            <Badge tone="ochre">{t("chat.panels.web.cached")}</Badge>
          ) : null}
          {truncated && !hasMore && !sourceTruncated ? (
            <Badge tone="neutral">{t("chat.panels.web.truncated")}</Badge>
          ) : null}
          {hasMore ? (
            <Badge tone="ochre">{t("chat.panels.web.morePages")}</Badge>
          ) : null}
          {sourceTruncated ? (
            <Badge tone="neutral">
              {t("chat.panels.web.sourceTruncated")}
            </Badge>
          ) : null}
        </div>
      </header>

      {content ? (
        <pre className="pi-web-fetch__content">{content}</pre>
      ) : (
        <PanelEmpty
          icon="external"
          title={t("chat.panels.web.noBodyTitle")}
          detail={t("chat.panels.web.noBodyDetail")}
        />
      )}

      <footer className="pi-web__foot">
        {content ? (
          <CopyButton
            value={content}
            label={t("chat.panels.web.copyContent")}
          />
        ) : null}
        {url ? (
          <CopyButton value={url} label={t("chat.panels.web.copyUrl")} />
        ) : null}
        {url ? (
          <a
            className="pi-web__open"
            href={url}
            target="_blank"
            rel="noreferrer noopener"
          >
            {t("chat.panels.web.openSource")}
            <Icon name="external" size={12} />
          </a>
        ) : null}
      </footer>
    </div>
  );
}
