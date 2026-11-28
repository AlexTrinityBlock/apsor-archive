import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

const SOURCE_URL = "https://github.com/AlexTrinityBlock/apsor-archive";

/** The author introduction, license line, and public source link. */
export function AuthorCard() {
  const { t } = useI18n();
  return (
    <div className="about-author">
      <span className="about-author__mark" aria-hidden="true">
        A
      </span>
      <div className="about-author__body">
        <p className="about-author__name">{t("insights.about.author.name")}</p>
        <p className="about-muted">{t("insights.about.author.role")}</p>
        <p>{t("insights.about.author.body")}</p>
        <p className="about-muted">{t("insights.about.author.license")}</p>
        <a
          className="text-link about-author__link"
          href={SOURCE_URL}
          target="_blank"
          rel="noreferrer noopener"
        >
          {t("insights.about.author.sourceLink")}
          <Icon name="external" size={13} aria-hidden="true" />
          <span className="visually-hidden">
            {" "}
            {t("insights.about.author.opensNewTab")}
          </span>
        </a>
      </div>
    </div>
  );
}
