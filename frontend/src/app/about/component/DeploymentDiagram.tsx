import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

const DATA_CHIPS = ["PostgreSQL 17", "Valkey", "RabbitMQ", "RustFS / S3"] as const;

/** Figure 3: browser → Cloudflare → (machine: tunnel → Caddy → app → data). */
export function DeploymentDiagram() {
  const { t } = useI18n();
  const captionId = "about-deploy-caption";

  return (
    <>
      <figure className="about-figure about-deploy" aria-labelledby={captionId}>
        <ol className="about-deploy__chain">
          <li className="about-node about-deploy__node">
            <h3>{t("insights.about.deploy.browser")}</h3>
            <p className="about-muted">{t("insights.about.deploy.exampleHost")}</p>
            <code className="about-chip about-chip--code">archive.example.com</code>
          </li>
          <li className="about-node about-deploy__node">
            <h3>{t("insights.about.deploy.edge")}</h3>
            <p>{t("insights.about.deploy.edgeDetail")}</p>
          </li>
          <li className="about-deploy__machine">
            <p className="about-frame-label">
              <span>{t("insights.about.deploy.machineLabel")}</span>
            </p>
            <ol className="about-deploy__inner">
              <li className="about-node about-deploy__node about-deploy__node--tunnel">
                <h3>
                  {t("insights.about.deploy.tunnel")}{" "}
                  <Icon name="arrow-up-right" size={13} aria-hidden="true" />
                </h3>
                <p>{t("insights.about.deploy.tunnelDetail")}</p>
              </li>
              <li className="about-node about-deploy__node">
                <h3>Caddy</h3>
                <p>{t("insights.about.deploy.caddyDetail")}</p>
              </li>
              <li className="about-node about-deploy__node">
                <h3>Apsor Archive</h3>
                <p>{t("insights.about.deploy.appDetail")}</p>
                <span className="about-deploy__chips">
                  <span className="about-chip">API</span>
                  <span className="about-chip">worker</span>
                </span>
              </li>
              <li className="about-node about-deploy__node">
                <h3>{t("insights.about.deploy.data")}</h3>
                <p>{t("insights.about.deploy.dataDetail")}</p>
                <span className="about-deploy__chips">
                  {DATA_CHIPS.map((chip) => (
                    <span className="about-chip" key={chip}>
                      {chip}
                    </span>
                  ))}
                </span>
              </li>
            </ol>
          </li>
        </ol>
        <figcaption id={captionId} className="about-figure__caption">
          {t("insights.about.deploy.caption")}
        </figcaption>
      </figure>
      <ul className="about-deploy__notes">
        <li>{t("insights.about.deploy.noteTunnel")}</li>
        <li>{t("insights.about.deploy.noteSetup")}</li>
      </ul>
    </>
  );
}
