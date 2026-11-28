import type { ReactNode } from "react";

import "./shared.css";

interface PageHeaderProps {
  readonly eyebrow: string;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly actions?: ReactNode;
  readonly meta?: ReactNode;
  /** Use 2 when the page already renders its own visually hidden h1. */
  readonly headingLevel?: 1 | 2;
}

/** Standard page masthead: mono eyebrow, sans title, quiet meta and actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
  headingLevel = 1,
}: PageHeaderProps) {
  const Heading = headingLevel === 2 ? "h2" : "h1";
  return (
    <header className="page-header">
      <div className="header-top page-header__kicker">
        <p className="eyebrow">{eyebrow}</p>
        {meta ? <span className="page-header__meta">{meta}</span> : null}
      </div>
      <div className="page-header__row">
        <div className="page-header__copy">
          <Heading className="page-title">{title}</Heading>
          {description ? (
            <p className="page-desc page-header__description">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
