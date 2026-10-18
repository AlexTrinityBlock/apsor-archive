import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Icon } from "../../component/Icon";
import { ThemeToggle } from "../../component/ThemeToggle";

interface ViewerShellProps {
  readonly kind: string;
  readonly title: string;
  readonly path?: string;
  readonly backTo: string;
  readonly backLabel: string;
  readonly actions?: ReactNode;
  readonly meta?: ReactNode;
  readonly children: ReactNode;
}

/**
 * The standalone viewer chrome.
 *
 * Viewer routes live outside `AppShell`, so this bar owns the back link, the
 * resource identity, and the theme control. It is the only fixed chrome; the
 * document stage below it scrolls naturally on mobile.
 */
export function ViewerShell({
  kind,
  title,
  path,
  backTo,
  backLabel,
  actions,
  meta,
  children,
}: ViewerShellProps) {
  return (
    <div className="viewer">
      <a className="skip-link" href="#viewer-main">
        Skip to the resource
      </a>
      <header className="viewer-bar">
        <div className="viewer-bar__lead">
          <Link to={backTo} className="viewer-bar__back">
            <Icon name="arrow-right" size={15} className="viewer-back-icon" />
            <span>{backLabel}</span>
          </Link>
          <span className="viewer-bar__rule" aria-hidden="true" />
          <Link to="/" className="viewer-bar__brand">
            <span>DendroMatrix</span>
            <span className="viewer-bar__brand-tag">Viewer</span>
          </Link>
        </div>
        <div className="viewer-bar__actions">
          {actions}
          <ThemeToggle compact className="viewer-bar__theme" />
        </div>
      </header>

      <div className="viewer-heading">
        <div className="viewer-heading__copy">
          <p className="eyebrow">{kind}</p>
          <h1 className="viewer-heading__title">{title}</h1>
          {path ? <code className="viewer-heading__path">{path}</code> : null}
        </div>
        {meta ? <div className="viewer-heading__meta">{meta}</div> : null}
      </div>

      <main id="viewer-main" className="viewer-main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
