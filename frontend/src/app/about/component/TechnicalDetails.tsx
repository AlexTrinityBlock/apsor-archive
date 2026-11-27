import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";

const PARAGRAPHS: readonly TranslationKey[] = [
  "insights.about.tech.ingest",
  "insights.about.tech.storage",
  "insights.about.tech.retrieval",
  "insights.about.tech.agent",
  "insights.about.tech.web",
];

const CITATION_FORMATS = ["[file:id#chunk]", "[memory:id]", "[summary:id]"] as const;

/** Collapsible implementation notes for technical readers. */
export function TechnicalDetails() {
  const { t } = useI18n();
  return (
    <details className="about-tech">
      <summary>{t("insights.about.tech.summary")}</summary>
      <div className="about-tech__body">
        {PARAGRAPHS.map((key) => (
          <p key={key}>{t(key)}</p>
        ))}
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
