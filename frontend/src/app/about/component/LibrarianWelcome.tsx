import { useI18n } from "../../i18n";
import { LibrarianPortrait } from "./LibrarianPortrait";

/** Vellum's welcome in the hero: her portrait beside a short spoken note. */
export function LibrarianWelcome() {
  const { t } = useI18n();
  return (
    <figure className="about-welcome" aria-label={t("insights.about.hero.welcomeLabel")}>
      <LibrarianPortrait
        id="vellum"
        alt={t("insights.about.hero.portraitAlt")}
        size={112}
        className="about-welcome__portrait"
      />
      <div className="about-welcome__body">
        <blockquote className="about-welcome__quote">
          <p>{t("insights.about.hero.welcome1")}</p>
          <p>{t("insights.about.hero.welcome2")}</p>
          <p>{t("insights.about.hero.welcome3")}</p>
        </blockquote>
        <figcaption className="about-welcome__signature">
          — {t("insights.about.hero.signature")}
        </figcaption>
      </div>
    </figure>
  );
}
