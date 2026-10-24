import type { ReactNode } from "react";

import { TreeMark } from "../../component/TreeMark";
import { TreeRings } from "../../component/TreeRings";
import "../auth.css";

interface AuthFrameProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
  readonly footer?: ReactNode;
}

/**
 * The public threshold of the archive: a paper field, an ink masthead, and one
 * quiet form. It deliberately sits outside AppShell so no navigation leaks
 * before sign-in.
 */
export function AuthFrame({
  eyebrow,
  title,
  description,
  children,
  footer,
}: AuthFrameProps) {
  return (
    <main className="auth-screen">
      <div className="auth-screen__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>

      <div className="auth-shell">
        <section className="auth-aside" aria-label="DendroMatrix">
          <div className="auth-aside__rings" aria-hidden="true">
            <TreeRings variant="quiet" />
          </div>

          <header className="auth-brand">
            <span className="auth-brand__seal">
              <TreeMark size={28} />
            </span>
            <span className="auth-brand__meta">
              <span className="auth-brand__name">DendroMatrix</span>
              <span className="auth-brand__sub">Archive Studio</span>
            </span>
          </header>

          <div className="auth-aside__copy">
            <p className="eyebrow">Private field station · Vol. 01</p>
            <p className="auth-aside__headline">
              Memory is not data.
              <span>It is growth.</span>
            </p>
            <p>
              A local-first archive of files, memories, and the passages between
              them. One keeper; no cloud account; the rings stay on this machine.
            </p>
            <ul className="auth-aside__facts">
              <li>Local-first</li>
              <li>Single keeper</li>
              <li>No telemetry</li>
            </ul>
          </div>

          <footer className="auth-aside__foot">
            <span>0.7px hairline protocol</span>
            <span>MMXXVI</span>
          </footer>
        </section>

        <section className="auth-form-panel">
          <div className="auth-form-panel__inner">
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            <p className="auth-form-panel__description">{description}</p>
            {children}
            {footer ? <div className="auth-form-panel__footer">{footer}</div> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
