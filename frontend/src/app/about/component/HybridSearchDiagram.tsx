import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

const TEXT_RESULT_KEYS = [
  "insights.method.hybridDiagram.chunkA",
  "insights.method.hybridDiagram.chunkB",
] as const;

const VECTOR_RESULT_KEYS = [
  "insights.method.hybridDiagram.chunkB",
  "insights.method.hybridDiagram.chunkC",
] as const;

/** Figure 03: two candidate lanes, one fusion, one deduplicated answer set. */
export function HybridSearchDiagram() {
  const { t } = useI18n();
  return (
    <figure className="method-figure">
      <div className="hybrid-diagram">
        <div className="hybrid-query">
          <span className="hybrid-query__icon" aria-hidden="true">
            <Icon name="search" size={17} />
          </span>
          <div>
            <span className="figure-label">
              {t("insights.method.hybridDiagram.queryLabel")}
            </span>
            <code>&quot;{t("insights.method.hybridDiagram.queryExample")}&quot;</code>
          </div>
          <Badge tone="ink">
            {t("insights.method.hybridDiagram.resultNumber")}
          </Badge>
        </div>

        <div className="hybrid-lanes">
          <div className="hybrid-lane">
            <header>
              <span className="figure-label">
                {t("insights.method.hybridDiagram.textLane")}
              </span>
              <Badge tone="moss">BM25</Badge>
            </header>
            <ul>
              {TEXT_RESULT_KEYS.map((resultKey, index) => (
                <li key={resultKey}>
                  <span>{t(resultKey)}</span>
                  <span className="hybrid-lane__rank">#{index + 1}</span>
                </li>
              ))}
            </ul>
            <p>{t("insights.method.hybridDiagram.textDetail")}</p>
          </div>
          <div className="hybrid-lane">
            <header>
              <span className="figure-label">
                {t("insights.method.hybridDiagram.vectorLane")}
              </span>
              <Badge tone="ochre">Cosine</Badge>
            </header>
            <ul>
              {VECTOR_RESULT_KEYS.map((resultKey, index) => (
                <li key={resultKey}>
                  <span>{t(resultKey)}</span>
                  <span className="hybrid-lane__rank">#{index + 1}</span>
                </li>
              ))}
            </ul>
            <p>{t("insights.method.hybridDiagram.vectorDetail")}</p>
          </div>
        </div>

        <div className="hybrid-fuse">
          <div className="hybrid-fuse__label">
            <span className="figure-label">
              {t("insights.method.hybridDiagram.fusionLabel")}
            </span>
            <code>score = Σ 1 / (60 + rank)</code>
          </div>
          <span className="hybrid-fuse__arrow" aria-hidden="true">
            <Icon name="arrow-down" size={16} />
          </span>
          <div className="hybrid-fuse__key">
            <span>{t("insights.method.hybridDiagram.deduplicateBy")}</span>
            <code>(source_kind, source_id, chunk_index)</code>
          </div>
        </div>

        <div className="hybrid-output">
          <div
            className="hybrid-output__items"
            aria-label={t("insights.method.hybridDiagram.outputAria")}
          >
            <span className="hybrid-chip">
              {t("insights.method.hybridDiagram.chunkA")}
            </span>
            <span className="hybrid-chip is-shared">
              {t("insights.method.hybridDiagram.chunkB")}
              <small>{t("insights.method.hybridDiagram.foundTwice")}</small>
            </span>
            <span className="hybrid-chip">
              {t("insights.method.hybridDiagram.chunkC")}
            </span>
          </div>
          <div className="hybrid-output__limit">
            <span>{t("insights.method.hybridDiagram.perKind")}</span>
            <strong>≤ 2</strong>
            <span>{t("insights.method.hybridDiagram.kinds")}</span>
          </div>
        </div>
      </div>
      <figcaption>
        {t("insights.method.hybridDiagram.captionBefore")}
        <code> matched_by </code>
        {t("insights.method.hybridDiagram.captionAfter")}
      </figcaption>
    </figure>
  );
}
