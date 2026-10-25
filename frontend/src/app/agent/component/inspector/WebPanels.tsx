import { Badge } from "../../../component/Badge";
import { Icon } from "../../../component/Icon";
import { CopyButton } from "../../../component/CopyButton";
import { formatDateTime } from "../../../../lib/format";
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
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Waiting for the public search results." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="search"
        title="The public search did not answer"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  const data = item.data;
  const query = textField(data, "query") ?? textField(item.arguments, "query") ?? "";
  const provider = textField(data, "provider") ?? "web search";
  const retrievedAt = textField(data, "retrieved_at");
  const results = webResults(data);
  const cached = data?.cached === true;
  const truncated = data?.truncated === true || data?.tool_truncated === true;

  return (
    <div className="pi-web">
      <header className="pi-web__head">
        <div className="pi-web__heading">
          <p className="eyebrow">Public web search</p>
          <strong>{query || "Untitled query"}</strong>
          <code>
            {provider}
            {retrievedAt ? ` · retrieved ${formatDateTime(retrievedAt)}` : ""}
          </code>
        </div>
        <div className="pi-web__badges">
          {cached ? <Badge tone="ochre">Cached</Badge> : null}
          {truncated ? <Badge tone="neutral">Truncated</Badge> : null}
          <Badge tone={results.length > 0 ? "moss" : "neutral"}>
            {results.length} {results.length === 1 ? "result" : "results"}
          </Badge>
        </div>
      </header>

      {results.length === 0 ? (
        <PanelEmpty
          icon="search"
          title="No public results were recorded"
          detail="The provider returned an empty result set for this query."
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
                  {result.title || result.url || "Untitled result"}
                  <Icon name="external" size={12} />
                </a>
                {result.url ? (
                  <CopyButton
                    value={result.url}
                    label="Copy URL"
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
                  score {result.score.toFixed(3)}
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
  if (item.live || item.status.toLowerCase() === "running") {
    return <LivePanel item={item} detail="Waiting for the fetched page body." />;
  }
  if (item.status.toLowerCase() === "error") {
    return (
      <PanelEmpty
        icon="external"
        title="The page could not be fetched"
        detail={item.detail ?? "No structured result was recorded."}
      />
    );
  }

  const data = item.data;
  const url =
    textField(data, "url") ?? textField(item.arguments, "url") ?? "";
  const provider = textField(data, "provider") ?? "web fetch";
  const retrievedAt = textField(data, "retrieved_at");
  const content = textField(data, "content") ?? "";
  const chars = numberField(data, "content_chars");
  const cached = data?.cached === true;
  const truncated = data?.truncated === true || data?.tool_truncated === true;

  return (
    <div className="pi-web">
      <header className="pi-web__head">
        <div className="pi-web__heading">
          <p className="eyebrow">Public web fetch</p>
          <a
            className="pi-web__url"
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            title={url}
          >
            {url || "Untitled URL"}
            <Icon name="external" size={12} />
          </a>
          <code>
            {provider}
            {retrievedAt ? ` · retrieved ${formatDateTime(retrievedAt)}` : ""}
            {chars !== null ? ` · ${chars.toLocaleString()} chars` : ""}
          </code>
        </div>
        <div className="pi-web__badges">
          {cached ? <Badge tone="ochre">Cached</Badge> : null}
          {truncated ? <Badge tone="neutral">Truncated</Badge> : null}
        </div>
      </header>

      {content ? (
        <pre className="pi-web-fetch__content">{content}</pre>
      ) : (
        <PanelEmpty
          icon="external"
          title="No page body was stored in this result"
          detail="This record predates the inline fetch preview, or the provider returned an empty body. Open the source URL to read it."
        />
      )}

      <footer className="pi-web__foot">
        {content ? <CopyButton value={content} label="Copy content" /> : null}
        {url ? <CopyButton value={url} label="Copy URL" /> : null}
        {url ? (
          <a
            className="pi-web__open"
            href={url}
            target="_blank"
            rel="noreferrer noopener"
          >
            Open source
            <Icon name="external" size={12} />
          </a>
        ) : null}
      </footer>
    </div>
  );
}
