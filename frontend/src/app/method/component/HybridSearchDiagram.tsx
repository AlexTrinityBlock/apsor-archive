import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";

const TEXT_RESULTS = ["chunk A", "chunk B"];
const VECTOR_RESULTS = ["chunk B", "chunk C"];

/** Figure 03: two candidate lanes, one fusion, one deduplicated answer set. */
export function HybridSearchDiagram() {
  return (
    <figure className="method-figure">
      <div className="hybrid-diagram">
        <div className="hybrid-query">
          <span className="hybrid-query__icon" aria-hidden="true">
            <Icon name="search" size={17} />
          </span>
          <div>
            <span className="figure-label">Query</span>
            <code>&quot;when did my thinking about urban trees change?&quot;</code>
          </div>
          <Badge tone="ink">result_number = 2</Badge>
        </div>

        <div className="hybrid-lanes">
          <div className="hybrid-lane">
            <header>
              <span className="figure-label">Text lane</span>
              <Badge tone="moss">BM25</Badge>
            </header>
            <ul>
              {TEXT_RESULTS.map((result, index) => (
                <li key={result}>
                  <span>{result}</span>
                  <span className="hybrid-lane__rank">#{index + 1}</span>
                </li>
              ))}
            </ul>
            <p>bigrams · word n-grams · trigrams</p>
          </div>
          <div className="hybrid-lane">
            <header>
              <span className="figure-label">Vector lane</span>
              <Badge tone="ochre">Cosine</Badge>
            </header>
            <ul>
              {VECTOR_RESULTS.map((result, index) => (
                <li key={result}>
                  <span>{result}</span>
                  <span className="hybrid-lane__rank">#{index + 1}</span>
                </li>
              ))}
            </ul>
            <p>hashing embedder · 384 dimensions</p>
          </div>
        </div>

        <div className="hybrid-fuse">
          <div className="hybrid-fuse__label">
            <span className="figure-label">Reciprocal rank fusion</span>
            <code>score = Σ 1 / (60 + rank)</code>
          </div>
          <span className="hybrid-fuse__arrow" aria-hidden="true">
            <Icon name="arrow-down" size={16} />
          </span>
          <div className="hybrid-fuse__key">
            <span>Deduplicate by</span>
            <code>(source_kind, source_id, chunk_index)</code>
          </div>
        </div>

        <div className="hybrid-output">
          <div className="hybrid-output__items" aria-label="Deduplicated results">
            <span className="hybrid-chip">chunk A</span>
            <span className="hybrid-chip is-shared">
              chunk B
              <small>found twice · returned once</small>
            </span>
            <span className="hybrid-chip">chunk C</span>
          </div>
          <div className="hybrid-output__limit">
            <span>Per source kind</span>
            <strong>≤ 2</strong>
            <span>files · memories · summaries</span>
          </div>
        </div>
      </div>
      <figcaption>
        Figure 03 — Hybrid retrieval. Both lanes contribute, duplicates collapse,
        and the final set is capped per source kind. The response carries
        <code> matched_by </code> and fusion counts.
      </figcaption>
    </figure>
  );
}
