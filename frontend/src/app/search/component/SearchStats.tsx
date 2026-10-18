import type { SearchStatsSchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import { Badge } from "../../component/Badge";

interface SearchStatsProps {
  readonly stats: SearchStatsSchema;
  readonly elapsedMs: number;
  readonly resultNumber: number;
}

/** The retrieval diagnostic rail: honest counts before and after fusion. */
export function SearchStats({ stats, elapsedMs, resultNumber }: SearchStatsProps) {
  return (
    <section className="search-stats" aria-labelledby="search-stats-title">
      <header className="search-stats__head">
        <div>
          <p className="eyebrow">Retrieval diagnostics</p>
          <h2 id="search-stats-title">What the two lanes did.</h2>
        </div>
        <Badge tone="moss">N = {resultNumber}</Badge>
      </header>

      <dl className="search-stats__grid">
        <div className="search-stat">
          <dt>Text candidates</dt>
          <dd>
            {formatNumber(stats.text_candidates)}
            <small>BM25, top N per kind</small>
          </dd>
        </div>
        <div className="search-stat">
          <dt>Vector candidates</dt>
          <dd>
            {formatNumber(stats.vector_candidates)}
            <small>Cosine, top N per kind</small>
          </dd>
        </div>
        <div className="search-stat">
          <dt>Merged</dt>
          <dd>
            {formatNumber(stats.merged)}
            <small>Union before dedup</small>
          </dd>
        </div>
        <div className="search-stat">
          <dt>Deduplicated</dt>
          <dd>
            {formatNumber(stats.deduplicated)}
            <small>Duplicate hits removed</small>
          </dd>
        </div>
        <div className="search-stat">
          <dt>Chunks scanned</dt>
          <dd>
            {formatNumber(stats.chunks_scanned)}
            <small>Current corpus</small>
          </dd>
        </div>
        <div className="search-stat">
          <dt>Elapsed</dt>
          <dd>
            {formatNumber(elapsedMs)}
            <small>Server milliseconds</small>
          </dd>
        </div>
      </dl>

      <p className="search-stats__note">
        Files, memories, and summaries each contribute up to N candidates per
        lane, so <code>text_candidates</code> can reach 3 × N. Both lanes are
        merged, duplicate grains collapse to one, and reciprocal-rank fusion
        (1 / (60 + rank)) orders what remains. These are candidate counts, not
        delivered results.
      </p>
    </section>
  );
}
