import type { ReactNode } from "react";

interface AboutSectionProps {
  readonly id: string;
  readonly number: string;
  readonly eyebrow: string;
  readonly title: string;
  /** A one-line librarian quotation that maps the section to the archive's world. */
  readonly epigraph?: string;
  readonly epigraphBy?: string;
  readonly intro?: string;
  readonly children: ReactNode;
}

/** One numbered About section: an `h2` landmark, an epigraph, and an intro. */
export function AboutSection({
  id,
  number,
  eyebrow,
  title,
  epigraph,
  epigraphBy,
  intro,
  children,
}: AboutSectionProps) {
  const titleId = `${id}-title`;
  return (
    <section className="about-section" id={id} aria-labelledby={titleId}>
      <header className="about-section__head">
        <span className="about-section__number" aria-hidden="true">
          {number}
        </span>
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2 id={titleId} tabIndex={-1}>
            {title}
          </h2>
        </div>
      </header>
      {epigraph ? (
        <figure className="about-epigraph">
          <blockquote>
            <p>{epigraph}</p>
          </blockquote>
          {epigraphBy ? <figcaption>— {epigraphBy}</figcaption> : null}
        </figure>
      ) : null}
      {intro ? <p className="about-section__intro">{intro}</p> : null}
      {children}
    </section>
  );
}
