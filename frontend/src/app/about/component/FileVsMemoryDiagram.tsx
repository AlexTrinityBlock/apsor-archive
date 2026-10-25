import { Badge } from "../../component/Badge";
import { useI18n } from "../../i18n";

/** Figure 01: the two provenance shapes, side by side. */
export function FileVsMemoryDiagram() {
  const { t } = useI18n();
  return (
    <figure className="method-figure">
      <div className="library-pair">
        <div className="library-pane library-pane--file">
          <header className="library-pane__head">
            <div>
              <span className="figure-label">
                {t("insights.method.fileDiagram.fileLabel")}
              </span>
              <h3>{t("insights.method.fileDiagram.fileTitle")}</h3>
            </div>
            <Badge tone="moss">
              {t("insights.method.fileDiagram.fileBadge")}
            </Badge>
          </header>
          <div
            className="mini-tree"
            aria-label={t("insights.method.fileDiagram.treeAria")}
          >
            <div className="mini-tree__row depth-0">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">/history</span>
              <span className="mini-tree__kind">
                {t("insights.method.fileDiagram.folder")}
              </span>
            </div>
            <div className="mini-tree__row depth-1">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">/industry</span>
              <span className="mini-tree__kind">
                {t("insights.method.fileDiagram.folder")}
              </span>
            </div>
            <div className="mini-tree__row depth-2">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">/automobiles</span>
              <span className="mini-tree__kind">
                {t("insights.method.fileDiagram.folder")}
              </span>
            </div>
            <div className="mini-tree__row depth-3 is-current">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">2026_automobile_history.md</span>
              <span className="mini-tree__kind">v3</span>
            </div>
            <div className="mini-tree__row depth-3 is-current">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">2024_ev_industry.pdf</span>
              <span className="mini-tree__kind">v1</span>
            </div>
            <div className="mini-tree__row depth-3 is-history">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">2022_automobile_annual.md</span>
              <span className="mini-tree__kind">v2</span>
            </div>
          </div>
          <footer className="library-pane__foot">
            <span>{t("insights.method.fileDiagram.softDelete")}</span>
            <span aria-hidden="true">/</span>
            <span>{t("insights.method.fileDiagram.versionsBranch")}</span>
          </footer>
        </div>

        <div className="library-pane library-pane--memory">
          <header className="library-pane__head">
            <div>
              <span className="figure-label">
                {t("insights.method.fileDiagram.memoryLabel")}
              </span>
              <h3>{t("insights.method.fileDiagram.memoryTitle")}</h3>
            </div>
            <Badge tone="ochre">
              {t("insights.method.fileDiagram.memoryBadge")}
            </Badge>
          </header>
          <div
            className="mini-axis"
            aria-label={t("insights.method.fileDiagram.axisAria")}
          >
            <div className="mini-axis__line" aria-hidden="true" />
            <div className="mini-axis__event is-active">
              <span className="mini-axis__dot" aria-hidden="true" />
              <time>{t("insights.method.fileDiagram.memoryOneTime")}</time>
              <span className="mini-axis__copy">
                {t("insights.method.fileDiagram.memoryOneCopy")}
              </span>
              <span className="mini-axis__id">memory:940</span>
            </div>
            <div className="mini-axis__event is-deprecated">
              <span className="mini-axis__dot" aria-hidden="true" />
              <time>{t("insights.method.fileDiagram.memoryTwoTime")}</time>
              <span className="mini-axis__copy">
                {t("insights.method.fileDiagram.memoryTwoCopy")}
              </span>
              <span className="mini-axis__id">memory:997</span>
            </div>
            <div className="mini-axis__event is-active">
              <span className="mini-axis__dot" aria-hidden="true" />
              <time>{t("insights.method.fileDiagram.memoryThreeTime")}</time>
              <span className="mini-axis__copy">
                {t("insights.method.fileDiagram.memoryThreeCopy")}
              </span>
              <span className="mini-axis__id">memory:1015</span>
            </div>
          </div>
          <footer className="library-pane__foot">
            <span>{t("insights.method.fileDiagram.supersedeChain")}</span>
            <span aria-hidden="true">/</span>
            <span>{t("insights.method.fileDiagram.traceOpen")}</span>
          </footer>
        </div>
      </div>
      <figcaption>
        {t("insights.method.fileDiagram.captionBefore")}
        <em>{t("insights.method.fileDiagram.captionWhere")}</em>
        {t("insights.method.fileDiagram.captionMiddle")}
        <em>{t("insights.method.fileDiagram.captionWhen")}</em>
        {t("insights.method.fileDiagram.captionAfter")}
      </figcaption>
    </figure>
  );
}
