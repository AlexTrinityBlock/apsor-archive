import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";

/**
 * Technical terms are product and protocol names, so they stay literal in
 * every locale; each one is followed by a plain one-line explanation.
 */
const TERMS: readonly { term: string; plain: TranslationKey; detail: TranslationKey }[] = [
  {
    term: "Ingestion worker",
    plain: "insights.about.tech.workerPlain",
    detail: "insights.about.tech.workerDetail",
  },
  {
    term: "PostgreSQL 17 · Valkey",
    plain: "insights.about.tech.dbPlain",
    detail: "insights.about.tech.dbDetail",
  },
  {
    term: "RustFS · Cloudflare R2 · S3",
    plain: "insights.about.tech.storagePlain",
    detail: "insights.about.tech.storageDetail",
  },
  {
    term: "WebP thumbnails",
    plain: "insights.about.tech.thumbPlain",
    detail: "insights.about.tech.thumbDetail",
  },
  {
    term: "BM25 + embeddings",
    plain: "insights.about.tech.searchPlain",
    detail: "insights.about.tech.searchDetail",
  },
  {
    term: "Reciprocal rank fusion (RRF)",
    plain: "insights.about.tech.rrfPlain",
    detail: "insights.about.tech.rrfDetail",
  },
  {
    term: "Agent · citations",
    plain: "insights.about.tech.agentPlain",
    detail: "insights.about.tech.agentDetail",
  },
  {
    term: "Row-level security (RLS)",
    plain: "insights.about.tech.rlsPlain",
    detail: "insights.about.tech.rlsDetail",
  },
  {
    term: "Cloudflare Tunnel · Caddy",
    plain: "insights.about.tech.tunnelPlain",
    detail: "insights.about.tech.tunnelDetail",
  },
];

const CITATION_FORMATS = ["[file:id#chunk]", "[memory:id]", "[summary:id]"] as const;

/** Collapsible glossary for technical readers: term → plain line → detail. */
export function TechnicalDetails() {
  const { t } = useI18n();
  return (
    <details className="about-tech">
      <summary>{t("insights.about.tech.summary")}</summary>
      <div className="about-tech__body">
        <p>{t("insights.about.tech.intro")}</p>
        <dl className="about-tech__terms">
          {TERMS.map((item) => (
            <div className="about-tech__term" key={item.term}>
              <dt>
                <code>{item.term}</code>
                <span className="about-tech__plain">{t(item.plain)}</span>
              </dt>
              <dd>{t(item.detail)}</dd>
            </div>
          ))}
        </dl>
        <p className="about-tech__formats">
          <span>{t("insights.about.tech.citationFormatsLabel")}</span>
          {CITATION_FORMATS.map((format) => (
            <code className="about-chip about-chip--code" key={format}>
              {format}
            </code>
          ))}
        </p>
      </div>
    </details>
  );
}
