import { Link } from "react-router-dom";

import { Icon } from "../component/Icon";
import { useI18n } from "../i18n";
import { FileVsMemoryDiagram } from "./component/FileVsMemoryDiagram";
import { HybridSearchDiagram } from "./component/HybridSearchDiagram";
import "./method.css";

/**
 * The About essay: two provenance shapes, one retrieval index, and the
 * citation contract that keeps answers inspectable.
 */
export function AboutPage() {
  const { t } = useI18n();

  const principles = [
    {
      index: "01",
      eyebrow: t("insights.method.principles.twoLibrariesEyebrow"),
      title: t("insights.method.principles.twoLibrariesTitle"),
      body: (
        <>
          <strong>
            {t("insights.method.principles.twoLibrariesFileLabel")}
          </strong>
          {t("insights.method.principles.twoLibrariesFileBody")}{" "}
          <strong>
            {t("insights.method.principles.twoLibrariesMemoryLabel")}
          </strong>
          {t("insights.method.principles.twoLibrariesMemoryBody")}
        </>
      ),
    },
    {
      index: "02",
      eyebrow: t("insights.method.principles.hybridEyebrow"),
      title: t("insights.method.principles.hybridTitle"),
      body: (
        <>
          {t("insights.method.principles.hybridBodyBefore")}
          <code>text_candidates</code>, <code>vector_candidates</code>,{" "}
          <code>merged</code>
          {t("insights.method.principles.hybridBodyAnd")}
          <code>deduplicated</code>
          {t("insights.method.principles.hybridBodyAfter")}
        </>
      ),
    },
    {
      index: "03",
      eyebrow: t("insights.method.principles.timelineEyebrow"),
      title: t("insights.method.principles.timelineTitle"),
      body: (
        <>
          {t("insights.method.principles.timelineBodyBefore")}
          <code>skips</code>
          {t("insights.method.principles.timelineBodyMid")}
          <code>density</code>
          {t("insights.method.principles.timelineBodyAfter")}
        </>
      ),
    },
    {
      index: "04",
      eyebrow: t("insights.method.principles.citationEyebrow"),
      title: t("insights.method.principles.citationTitle"),
      body: (
        <>
          {t("insights.method.principles.citationBodyBefore")}
          <code>[file:12#15]</code>
          {t("insights.method.principles.citationBodyOr")}
          <code>[memory:1015]</code>
          {t("insights.method.principles.citationBodyAfter")}
          <code>503 ai_not_configured</code>
          {t("insights.method.principles.citationBodyTail")}
        </>
      ),
    },
  ] as const;

  const citationLoop = [
    {
      index: "01",
      title: t("insights.method.citation.retrieveTitle"),
      body: t("insights.method.citation.retrieveBody"),
    },
    {
      index: "02",
      title: t("insights.method.citation.answerTitle"),
      body: t("insights.method.citation.answerBody"),
    },
    {
      index: "03",
      title: t("insights.method.citation.verifyTitle"),
      body: t("insights.method.citation.verifyBody"),
    },
    {
      index: "04",
      title: t("insights.method.citation.keepTitle"),
      body: t("insights.method.citation.keepBody"),
    },
  ] as const;

  return (
    <div className="page method-page">
      <div className="content-container content-container--reading">
        <header className="method-hero">
          <div className="method-hero__top">
            <span className="shell-tag">{t("insights.method.hero.kicker")}</span>
            <span className="mono-label">
              {t("insights.method.hero.eyebrow")}
            </span>
          </div>
          <h1 className="method-hero__title">
            {t("insights.method.hero.titleLine1")}
            <span>
              {t("insights.method.hero.titleLine2Prefix")}
              <em>{t("insights.method.hero.titleAccent")}</em>
            </span>
          </h1>
          <p className="method-hero__lede">
            {t("insights.method.hero.lede")}
          </p>
          <p className="method-hero__note">
            <Icon name="info" size={15} />
            <span>{t("insights.method.hero.note")}</span>
          </p>
          <dl className="meta-grid method-meta">
            <div className="meta-item">
              <dt className="meta-key">{t("insights.method.hero.metaArchiveKey")}</dt>
              <dd className="meta-value">
                {t("insights.method.hero.metaArchiveValue")}
              </dd>
            </div>
            <div className="meta-item">
              <dt className="meta-key">
                {t("insights.method.hero.metaRetrievalKey")}
              </dt>
              <dd className="meta-value">
                {t("insights.method.hero.metaRetrievalValue")}
              </dd>
            </div>
            <div className="meta-item">
              <dt className="meta-key">{t("insights.method.hero.metaFusionKey")}</dt>
              <dd className="meta-value">
                {t("insights.method.hero.metaFusionValue")}
              </dd>
            </div>
            <div className="meta-item">
              <dt className="meta-key">
                {t("insights.method.hero.metaContractKey")}
              </dt>
              <dd className="meta-value">
                {t("insights.method.hero.metaContractValue")}
              </dd>
            </div>
          </dl>
        </header>

        <section className="method-principles" aria-labelledby="principles-title">
          <header className="method-block-head">
            <p className="eyebrow">{t("insights.method.principles.eyebrow")}</p>
            <h2 id="principles-title">
              {t("insights.method.principles.title")}
            </h2>
          </header>
          <div className="method-principles__grid">
            {principles.map((principle) => (
              <article className="principle-card" key={principle.index}>
                <span className="principle-card__num">
                  {principle.index} // {principle.eyebrow.toUpperCase()}
                </span>
                <h3 className="principle-card__title">{principle.title}</h3>
                <p className="principle-card__body">{principle.body}</p>
              </article>
            ))}
          </div>
        </section>

        <blockquote className="method-pullquote">
          <Icon name="quote" size={24} />
          <p>{t("insights.method.pullquote")}</p>
        </blockquote>

        <section
          className="method-section"
          id="two-libraries"
          aria-labelledby="two-libraries-title"
        >
          <header className="method-section__head">
            <span className="method-section__number">01</span>
            <div>
              <p className="eyebrow">
                {t("insights.method.twoLibraries.eyebrow")}
              </p>
              <h2 id="two-libraries-title">
                {t("insights.method.twoLibraries.title")}
              </h2>
            </div>
          </header>
          <div className="method-prose">
            <p>
              {t("insights.method.twoLibraries.paragraph1Before")}
              <code>/history/industry/automobiles</code>
              {t("insights.method.twoLibraries.paragraph1After")}
            </p>
            <p>{t("insights.method.twoLibraries.paragraph2")}</p>
            <p>{t("insights.method.twoLibraries.paragraph3")}</p>
          </div>
          <FileVsMemoryDiagram />
        </section>

        <section
          className="method-section"
          id="hybrid-search"
          aria-labelledby="hybrid-title"
        >
          <header className="method-section__head">
            <span className="method-section__number">02</span>
            <div>
              <p className="eyebrow">{t("insights.method.hybrid.eyebrow")}</p>
              <h2 id="hybrid-title">{t("insights.method.hybrid.title")}</h2>
            </div>
          </header>
          <div className="method-prose">
            <p>
              {t("insights.method.hybrid.paragraph1Before")}
              <em>{t("insights.method.hybrid.semanticExample")}</em>
              {t("insights.method.hybrid.paragraph1Middle")}
              <code>2026_automobile_history.md</code>
              {t("insights.method.hybrid.paragraph1After")}
            </p>
            <p>{t("insights.method.hybrid.paragraph2")}</p>
            <p>
              {t("insights.method.hybrid.paragraph3Before")}
              <code>matched_by</code>
              {t("insights.method.hybrid.paragraph3And")}
              <code>text_candidates</code>
              {t("insights.method.hybrid.paragraph3And")}
              <code>vector_candidates</code>
              {t("insights.method.hybrid.paragraph3And")}
              <code>merged</code>
              {t("insights.method.principles.hybridBodyAnd")}
              <code>deduplicated</code>
              {t("insights.method.hybrid.paragraph3After")}
            </p>
          </div>
          <HybridSearchDiagram />
          <aside className="method-note">
            <span className="method-note__marker" aria-hidden="true" />
            <div>
              <p className="eyebrow">
                {t("insights.method.hybrid.noteEyebrow")}
              </p>
              <p>{t("insights.method.hybrid.noteBody")}</p>
            </div>
          </aside>
        </section>

        <section
          className="method-section"
          id="citation-loop"
          aria-labelledby="citation-title"
        >
          <header className="method-section__head">
            <span className="method-section__number">03</span>
            <div>
              <p className="eyebrow">
                {t("insights.method.citation.eyebrow")}
              </p>
              <h2 id="citation-title">
                {t("insights.method.citation.title")}
              </h2>
            </div>
          </header>
          <div className="method-prose">
            <p>{t("insights.method.citation.paragraph")}</p>
          </div>
          <ol className="method-loop">
            {citationLoop.map((step) => (
              <li className="method-loop__step" key={step.index}>
                <span className="method-loop__index">{step.index}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="method-prose__closing">
            {t("insights.method.citation.closing")}
          </p>
        </section>

        <footer className="method-colophon">
          <div className="method-colophon__mark">
            <span className="shell-tag">{t("insights.method.colophon.tag")}</span>
            <p>{t("insights.method.colophon.line")}</p>
          </div>
          <nav
            className="method-colophon__links"
            aria-label={t("insights.method.colophon.linksAria")}
          >
            <Link className="text-link" to="/dashboard">
              {t("core.nav.dashboard")}
            </Link>
            <Link className="text-link" to="/questions">
              {t("insights.method.colophon.questions")}
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
