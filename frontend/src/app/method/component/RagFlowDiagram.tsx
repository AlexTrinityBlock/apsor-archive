import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";

/** Figure 06: how a question becomes a grounded, citable answer. */
export function RagFlowDiagram() {
  return (
    <figure className="method-figure">
      <div className="rag-flow">
        <div className="rag-step">
          <span className="rag-step__number">01</span>
          <div>
            <span className="figure-label">Question</span>
            <p>Ask across every current shelf.</p>
          </div>
        </div>
        <span className="rag-flow__arrow" aria-hidden="true">
          <Icon name="arrow-down" size={16} />
        </span>
        <div className="rag-step">
          <span className="rag-step__number">02</span>
          <div>
            <span className="figure-label">Hybrid retrieval</span>
            <p>Fused and deduplicated passages, each with provenance.</p>
          </div>
        </div>
        <span className="rag-flow__arrow" aria-hidden="true">
          <Icon name="arrow-down" size={16} />
        </span>
        <div className="rag-step">
          <span className="rag-step__number">03</span>
          <div>
            <span className="figure-label">DeepSeek</span>
            <p>Answer only from the excerpts. Refuse to invent the missing.</p>
          </div>
        </div>
        <span className="rag-flow__arrow" aria-hidden="true">
          <Icon name="arrow-down" size={16} />
        </span>
        <div className="rag-final">
          <div className="rag-final__answer">
            <span className="figure-label">Answer with receipts</span>
            <p>
              “Your position changed in June, when the path became the argument rather
              than the folder.”
            </p>
            <div className="citation-stack">
              <span className="citation citation--memory">
                <Icon name="memory" size={13} />[memory:1015]
              </span>
              <span className="citation citation--file">
                <Icon name="file" size={13} />[file:12#15]
              </span>
            </div>
          </div>
          <div className="rag-final__fallback">
            <Badge tone="vermilion">503</Badge>
            <div>
              <span className="figure-label">No key configured</span>
              <code>ai_not_configured</code>
              <p>No prose is invented to fill the silence.</p>
            </div>
          </div>
        </div>
      </div>
      <figcaption>
        Figure 06 — Retrieval-augmented answering. Citations are part of the
        response contract, not a decorative footer. Summaries record their
        generator in the same spirit.
      </figcaption>
    </figure>
  );
}
