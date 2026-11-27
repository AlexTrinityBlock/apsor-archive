import type { MouseEvent } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../component/Icon";
import type { IconName } from "../component/Icon";
import { useI18n } from "../i18n";
import type { TranslationKey } from "../i18n";
import { AboutSection } from "./component/AboutSection";
import { AuthorCard } from "./component/AuthorCard";
import { DataFlowDiagram } from "./component/DataFlowDiagram";
import { DeploymentDiagram } from "./component/DeploymentDiagram";
import { PrivacyBoundaryDiagram } from "./component/PrivacyBoundaryDiagram";
import { TechnicalDetails } from "./component/TechnicalDetails";
import "./about.css";

const GLANCE: readonly { key: TranslationKey; value: TranslationKey }[] = [
  {
    key: "insights.about.hero.glancePrivacyKey",
    value: "insights.about.hero.glancePrivacyValue",
  },
  {
    key: "insights.about.hero.glanceAnswersKey",
    value: "insights.about.hero.glanceAnswersValue",
  },
  {
    key: "insights.about.hero.glanceHostingKey",
    value: "insights.about.hero.glanceHostingValue",
  },
  {
    key: "insights.about.hero.glanceLicenseKey",
    value: "insights.about.hero.glanceLicenseValue",
  },
];

const TOC: readonly { id: string; label: TranslationKey }[] = [
  { id: "about-what", label: "insights.about.toc.what" },
  { id: "about-flow", label: "insights.about.toc.flow" },
  { id: "about-privacy", label: "insights.about.toc.privacy" },
  { id: "about-deploy", label: "insights.about.toc.deploy" },
  { id: "about-author", label: "insights.about.toc.author" },
];

const WHAT_CARDS: readonly {
  icon: IconName;
  title: TranslationKey;
  body: TranslationKey;
}[] = [
  {
    icon: "folder",
    title: "insights.about.what.filesTitle",
    body: "insights.about.what.filesBody",
  },
  {
    icon: "memory",
    title: "insights.about.what.memoriesTitle",
    body: "insights.about.what.memoriesBody",
  },
  {
    icon: "chat",
    title: "insights.about.what.chatTitle",
    body: "insights.about.what.chatBody",
  },
];

/** Scrolls to a section inside the `.app-page` scroller and focuses its heading. */
function jumpTo(event: MouseEvent<HTMLAnchorElement>, id: string) {
  const target = document.getElementById(id);
  if (!target) {
    return;
  }
  event.preventDefault();
  target.scrollIntoView({ block: "start" });
  target.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
}

/**
 * About Apsor Archive: what it is, how data flows, the privacy boundary,
 * where it runs, and who made it — plain language first, detail on demand.
 */
export function AboutPage() {
  const { t } = useI18n();

  return (
    <div className="page about-page">
      <div className="content-container content-container--reading">
        <header className="about-hero" id="about-top">
          <span className="shell-tag">{t("insights.about.hero.kicker")}</span>
          <h1 className="about-hero__title">{t("insights.about.hero.title")}</h1>
          <p className="about-hero__lede">{t("insights.about.hero.lede")}</p>
          <div role="group" aria-label={t("insights.about.hero.glanceAria")}>
          <dl className="meta-grid about-glance">
            {GLANCE.map((item) => (
              <div className="meta-item" key={item.key}>
                <dt className="meta-key">{t(item.key)}</dt>
                <dd className="meta-value">{t(item.value)}</dd>
              </div>
            ))}
          </dl>
          </div>
          <nav className="about-toc" aria-label={t("insights.about.hero.tocAria")}>
            <ol>
              {TOC.map((item, index) => (
                <li key={item.id}>
                  <a href={`#${item.id}`} onClick={(event) => jumpTo(event, item.id)}>
                    <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                    {t(item.label)}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </header>

        <AboutSection
          id="about-what"
          number="01"
          eyebrow={t("insights.about.what.eyebrow")}
          title={t("insights.about.what.title")}
          intro={t("insights.about.what.intro")}
        >
          <ul className="about-cards">
            {WHAT_CARDS.map((card) => (
              <li className="about-card" key={card.title}>
                <Icon name={card.icon} size={18} aria-hidden="true" />
                <h3>{t(card.title)}</h3>
                <p>{t(card.body)}</p>
              </li>
            ))}
          </ul>
        </AboutSection>

        <AboutSection
          id="about-flow"
          number="02"
          eyebrow={t("insights.about.flow.eyebrow")}
          title={t("insights.about.flow.title")}
          intro={t("insights.about.flow.intro")}
        >
          <DataFlowDiagram />
          <TechnicalDetails />
        </AboutSection>

        <AboutSection
          id="about-privacy"
          number="03"
          eyebrow={t("insights.about.privacy.eyebrow")}
          title={t("insights.about.privacy.title")}
          intro={t("insights.about.privacy.intro")}
        >
          <PrivacyBoundaryDiagram />
        </AboutSection>

        <AboutSection
          id="about-deploy"
          number="04"
          eyebrow={t("insights.about.deploy.eyebrow")}
          title={t("insights.about.deploy.title")}
          intro={t("insights.about.deploy.intro")}
        >
          <DeploymentDiagram />
        </AboutSection>

        <AboutSection
          id="about-author"
          number="05"
          eyebrow={t("insights.about.author.eyebrow")}
          title={t("insights.about.author.title")}
        >
          <AuthorCard />
        </AboutSection>

        <footer className="about-colophon">
          <nav aria-label={t("insights.about.colophon.linksAria")}>
            <Link className="text-link" to="/chat">
              {t("insights.about.colophon.ask")}
            </Link>
            <Link className="text-link" to="/library">
              {t("core.nav.library")}
            </Link>
            <Link className="text-link" to="/settings">
              {t("core.nav.settings")}
            </Link>
          </nav>
        </footer>
      </div>
    </div>
  );
}
