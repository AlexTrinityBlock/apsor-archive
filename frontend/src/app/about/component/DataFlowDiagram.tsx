import type { IconName } from "../../component/Icon";
import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";

interface FlowNode {
  readonly key: string;
  readonly icon: IconName;
  readonly phase: "add" | "ask";
  readonly title: TranslationKey;
  readonly body: TranslationKey;
}

const NODES: readonly FlowNode[] = [
  {
    key: "upload",
    icon: "file",
    phase: "add",
    title: "insights.about.flow.uploadTitle",
    body: "insights.about.flow.uploadBody",
  },
  {
    key: "prepare",
    icon: "layers",
    phase: "add",
    title: "insights.about.flow.prepareTitle",
    body: "insights.about.flow.prepareBody",
  },
  {
    key: "store",
    icon: "database",
    phase: "add",
    title: "insights.about.flow.storeTitle",
    body: "insights.about.flow.storeBody",
  },
  {
    key: "search",
    icon: "search",
    phase: "ask",
    title: "insights.about.flow.searchTitle",
    body: "insights.about.flow.searchBody",
  },
  {
    key: "answer",
    icon: "chat",
    phase: "ask",
    title: "insights.about.flow.answerTitle",
    body: "insights.about.flow.answerBody",
  },
];

/** Figure 1: the five steps from upload to a cited answer, as an ordered list. */
export function DataFlowDiagram() {
  const { t } = useI18n();
  const captionId = "about-flow-caption";

  const tags = (key: string) => {
    switch (key) {
      case "prepare":
        return <span className="about-chip">{t("insights.about.flow.prepareTag")}</span>;
      case "store":
        return (
          <>
            <span className="about-chip">PostgreSQL</span>
            <span className="about-chip">{t("insights.about.flow.storeDiskTag")}</span>
          </>
        );
      case "search":
        return (
          <span className="about-lanes">
            <span className="about-chip">{t("insights.about.flow.laneWords")}</span>
            <span className="about-chip">{t("insights.about.flow.laneSimilar")}</span>
            <Icon name="arrow-down" size={12} aria-hidden="true" />
            <span className="about-chip about-chip--moss">RRF</span>
          </span>
        );
      case "answer":
        return <code className="about-chip about-chip--code">[file:12#3]</code>;
      default:
        return null;
    }
  };

  return (
    <figure className="about-figure about-flow" aria-labelledby={captionId}>
      <div className="about-flow__phases" aria-hidden="true">
        <span className="about-flow__phase about-flow__phase--add">
          {t("insights.about.flow.phaseAdd")}
        </span>
        <span className="about-flow__phase about-flow__phase--ask">
          {t("insights.about.flow.phaseAsk")}
        </span>
      </div>
      <ol className="about-flow__steps">
        {NODES.map((node, index) => (
          <li
            className={`about-flow__step about-flow__step--${node.phase}`}
            key={node.key}
          >
            <div className="about-flow__step-top">
              <span className="about-flow__badge" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <Icon name={node.icon} size={16} aria-hidden="true" />
            </div>
            <h3>{t(node.title)}</h3>
            <p>{t(node.body)}</p>
            <div className="about-flow__tags">{tags(node.key)}</div>
          </li>
        ))}
      </ol>
      <p className="about-flow__return">
        <Icon name="arrow-up" size={14} aria-hidden="true" />
        <span>{t("insights.about.flow.returnNote")}</span>
      </p>
      <figcaption id={captionId} className="about-figure__caption">
        {t("insights.about.flow.caption")}
      </figcaption>
    </figure>
  );
}
