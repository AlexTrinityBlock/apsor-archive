import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { TranslationKey } from "../../i18n";

const GUARANTEES: readonly { title: TranslationKey; body: TranslationKey }[] = [
  {
    title: "insights.about.privacy.ownerTitle",
    body: "insights.about.privacy.ownerBody",
  },
  {
    title: "insights.about.privacy.rootPointTitle",
    body: "insights.about.privacy.rootPointBody",
  },
  {
    title: "insights.about.privacy.impersonationPointTitle",
    body: "insights.about.privacy.impersonationPointBody",
  },
  {
    title: "insights.about.privacy.providerTitle",
    body: "insights.about.privacy.providerBody",
  },
  {
    title: "insights.about.privacy.secretsTitle",
    body: "insights.about.privacy.secretsBody",
  },
];

/** Figure 2 plus the guarantees list and an honest caveat. */
export function PrivacyBoundaryDiagram() {
  const { t } = useI18n();
  const captionId = "about-privacy-caption";

  return (
    <>
      <figure className="about-figure about-privacy" aria-labelledby={captionId}>
        <div className="about-privacy__top">
          <div className="about-node about-privacy__root">
            <Icon name="users" size={16} aria-hidden="true" />
            <div>
              <h3>{t("insights.about.privacy.rootTitle")}</h3>
              <p>{t("insights.about.privacy.rootBody")}</p>
              <span className="about-chip about-chip--seal">
                {t("insights.about.privacy.rootNoData")}
              </span>
            </div>
          </div>
          <div className="about-node about-privacy__impersonation">
            <Icon name="key" size={16} aria-hidden="true" />
            <div>
              <h3>{t("insights.about.privacy.impersonationTitle")}</h3>
              <p>{t("insights.about.privacy.impersonationBody")}</p>
            </div>
          </div>
        </div>
        <span className="about-privacy__stop" aria-hidden="true" />
        <div className="about-privacy__frame">
          <p className="about-frame-label">
            <Icon name="database" size={13} aria-hidden="true" />
            <span>{t("insights.about.privacy.databaseLabel")}</span>
          </p>
          <ul className="about-privacy__accounts">
            <li className="about-node about-privacy__account">
              <Icon name="user" size={16} aria-hidden="true" />
              <div>
                <h3>{t("insights.about.privacy.yourArchive")}</h3>
                <p>{t("insights.about.privacy.ownerYou")}</p>
                <p className="about-muted">{t("insights.about.privacy.contents")}</p>
              </div>
            </li>
            <li className="about-privacy__divider">
              <span className="about-privacy__deny" aria-hidden="true">
                <Icon name="close" size={14} />
              </span>
              <span>{t("insights.about.privacy.denied")}</span>
            </li>
            <li className="about-node about-privacy__account">
              <Icon name="user" size={16} aria-hidden="true" />
              <div>
                <h3>{t("insights.about.privacy.otherArchive")}</h3>
                <p>{t("insights.about.privacy.ownerOther")}</p>
                <p className="about-muted">{t("insights.about.privacy.contents")}</p>
              </div>
            </li>
          </ul>
        </div>
        <figcaption id={captionId} className="about-figure__caption">
          {t("insights.about.privacy.caption")}
        </figcaption>
      </figure>

      <ul className="about-guarantees">
        {GUARANTEES.map((item) => (
          <li key={item.title}>
            <Icon name="check" size={15} aria-hidden="true" />
            <div>
              <h3>{t(item.title)}</h3>
              <p>{t(item.body)}</p>
            </div>
          </li>
        ))}
      </ul>

      <aside className="about-note">
        <span className="about-note__marker" aria-hidden="true" />
        <div>
          <h3>{t("insights.about.privacy.caveatTitle")}</h3>
          <p>{t("insights.about.privacy.caveatBody")}</p>
        </div>
      </aside>
    </>
  );
}
