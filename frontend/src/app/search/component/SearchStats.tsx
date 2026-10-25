import type { SearchStatsSchema } from "../../generated-apis-types/schemas";
import { Badge } from "../../component/Badge";
import { Panel } from "../../component/Panel";
import { StatCard } from "../../component/StatCard";
import { useI18n } from "../../i18n";

interface SearchStatsProps {
  readonly stats: SearchStatsSchema;
  readonly elapsedMs: number;
}

/**
 * Honest retrieval diagnostics: real candidate counts before and after fusion,
 * the corpus size that was scanned, and the server-reported elapsed time.
 */
export function SearchStats({ stats, elapsedMs }: SearchStatsProps) {
  const { t, formatNumber } = useI18n();
  const totalCandidates = stats.text_candidates + stats.vector_candidates;
  const textShare = totalCandidates > 0 ? (stats.text_candidates / totalCandidates) * 100 : 0;
  const vectorShare = totalCandidates > 0 ? (stats.vector_candidates / totalCandidates) * 100 : 0;

  return (
    <Panel
      eyebrow={t("insights.search.stats.eyebrow")}
      title={t("insights.search.stats.title")}
      className="search-diagnostics"
      action={
        <div className="search-diagnostics__badges">
          <Badge tone="ochre">{t("insights.search.stats.rrf")}</Badge>
        </div>
      }
    >
      <div className="search-fusion">
        <div className="search-fusion__labels" aria-hidden="true">
          <span>{t("insights.search.stats.textLane")}</span>
          <span>{t("insights.search.stats.vectorLane")}</span>
        </div>
        <div className="search-fusion__track" aria-hidden="true">
          {totalCandidates > 0 ? (
            <>
              <span
                className="search-fusion__bar search-fusion__bar--text"
                style={{ width: `${textShare}%` }}
              />
              <span
                className="search-fusion__bar search-fusion__bar--vector"
                style={{ width: `${vectorShare}%` }}
              />
            </>
          ) : null}
        </div>
        <p className="search-fusion__note">
          {totalCandidates > 0
            ? t("insights.search.stats.barNote")
            : t("insights.search.stats.noCandidates")}
        </p>
      </div>

      <div className="search-metrics">
        <StatCard
          label={t("insights.search.stats.textCandidates")}
          value={formatNumber(stats.text_candidates)}
          note={t("insights.search.stats.textCandidatesNote")}
          accent="moss"
        />
        <StatCard
          label={t("insights.search.stats.vectorCandidates")}
          value={formatNumber(stats.vector_candidates)}
          note={t("insights.search.stats.vectorCandidatesNote")}
          accent="ochre"
        />
        <StatCard
          label={t("insights.search.stats.merged")}
          value={formatNumber(stats.merged)}
          note={t("insights.search.stats.mergedNote")}
          accent="ink"
        />
        <StatCard
          label={t("insights.search.stats.deduplicated")}
          value={formatNumber(stats.deduplicated)}
          note={t("insights.search.stats.deduplicatedNote")}
          accent="ink"
        />
        <StatCard
          label={t("insights.search.stats.chunksScanned")}
          value={formatNumber(stats.chunks_scanned)}
          note={t("insights.search.stats.chunksScannedNote")}
          accent="ink"
        />
        <StatCard
          label={t("insights.search.stats.elapsed")}
          value={`${formatNumber(elapsedMs)} ms`}
          note={t("insights.search.stats.elapsedNote")}
          accent="ink"
        />
      </div>

      <p className="search-diagnostics__note">
        {t("insights.search.stats.note")}
      </p>

      {stats.terms.length > 0 ? (
        <div className="search-diagnostics__terms">
          <span className="mono-label">{t("insights.search.stats.textTerms")}</span>
          {stats.terms.map((term, index) => (
            <span key={`${term}-${index}`} className="badge badge--neutral">
              {term}
            </span>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}
