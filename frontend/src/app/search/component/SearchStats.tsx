import type { SearchStatsSchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";
import { Panel } from "../../component/Panel";
import { StatCard } from "../../component/StatCard";

interface SearchStatsProps {
  readonly stats: SearchStatsSchema;
  readonly elapsedMs: number;
}

/**
 * Honest retrieval diagnostics: real candidate counts before and after fusion,
 * the corpus size that was scanned, and the server-reported elapsed time.
 */
export function SearchStats({ stats, elapsedMs }: SearchStatsProps) {
  const totalCandidates = stats.text_candidates + stats.vector_candidates;
  const textShare = totalCandidates > 0 ? (stats.text_candidates / totalCandidates) * 100 : 0;
  const vectorShare = totalCandidates > 0 ? (stats.vector_candidates / totalCandidates) * 100 : 0;

  return (
    <Panel
      eyebrow="Retrieval diagnostics"
      title="Dual-lane candidate fusion"
      className="search-diagnostics"
      action={
        <div className="search-diagnostics__badges">
          <Badge tone="ochre">RRF · 1 / (60 + rank)</Badge>
        </div>
      }
    >
      <div className="search-fusion">
        <div className="search-fusion__labels" aria-hidden="true">
          <span>Text lane · BM25</span>
          <span>Vector lane · dense</span>
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
            ? "Bar widths show each lane's share of the candidate pool before fusion."
            : "Neither lane returned a candidate for this query."}
        </p>
      </div>

      <div className="search-metrics">
        <StatCard
          label="Text candidates"
          value={formatNumber(stats.text_candidates)}
          note="BM25 · top N per kind"
          accent="moss"
        />
        <StatCard
          label="Vector candidates"
          value={formatNumber(stats.vector_candidates)}
          note="Cosine · top N per kind"
          accent="ochre"
        />
        <StatCard
          label="Merged"
          value={formatNumber(stats.merged)}
          note="Union of both lanes"
          accent="ink"
        />
        <StatCard
          label="Deduplicated"
          value={formatNumber(stats.deduplicated)}
          note="Duplicate hits collapsed"
          accent="ink"
        />
        <StatCard
          label="Chunks scanned"
          value={formatNumber(stats.chunks_scanned)}
          note="Current corpus"
          accent="ink"
        />
        <StatCard
          label="Elapsed"
          value={`${formatNumber(elapsedMs)} ms`}
          note="Server reported"
          accent="ink"
        />
      </div>

      <p className="search-diagnostics__note">
        Files, memories, and summaries each contribute up to N candidates per lane.
        Both lanes merge into one pool, duplicate chunks collapse, and reciprocal-rank
        fusion orders the survivors. These are candidate counts, not delivered results.
      </p>

      {stats.terms.length > 0 ? (
        <div className="search-diagnostics__terms">
          <span className="mono-label">Text terms</span>
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
