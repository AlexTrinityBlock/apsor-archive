import type { ReactNode } from "react";

interface PageHeaderProps {
  readonly eyebrow: string;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly actions?: ReactNode;
  readonly meta?: ReactNode;
}

/** Standard page masthead: mono kicker, serif title, quiet actions. */
export function PageHeader({ eyebrow, title, description, actions, meta }: PageHeaderProps) {
  return (
    <header className="page-header reveal reveal-1">
      <div className="page-header__kicker">
        <span className="eyebrow">{eyebrow}</span>
        <span className="hairline" aria-hidden="true" />
        {meta ? <span className="page-header__meta">{meta}</span> : null}
      </div>
      <div className="page-header__row">
        <div className="page-header__copy">
          <h1>{title}</h1>
          {description ? <p className="page-header__description">{description}</p> : null}
        </div>
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
