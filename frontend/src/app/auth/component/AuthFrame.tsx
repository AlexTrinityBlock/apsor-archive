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
 * The public face of the archive: one editorial panel, one quiet form. It is
 * deliberately outside AppShell so no navigation leaks before sign-in.
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
      <section className="auth-portrait" aria-label="DendroMatrix">
        <div className="auth-portrait__rings" aria-hidden="true">
          <TreeRings variant="hero" />
        </div>
        <header className="auth-portrait__brand">
          <TreeMark size={44} />
          <div>
            <p className="auth-portrait__name">DendroMatrix</p>
            <p className="auth-portrait__sub">Annual ring archive</p>
          </div>
        </header>
        <div className="auth-portrait__copy">
          <p className="eyebrow">Private field station · Vol. 01</p>
          <h1>
            Memory is not data.
            <span>It is growth.</span>
          </h1>
          <p>
            A local-first archive of files, memories, and the passages between them.
            One keeper; no cloud account; the rings stay on this machine.
          </p>
        </div>
        <footer className="auth-portrait__foot">
          <span>Local-first</span>
          <span aria-hidden="true">✦</span>
          <span>Single reader</span>
          <span aria-hidden="true">✦</span>
          <span>No telemetry</span>
        </footer>
      </section>

      <section className="auth-form-panel">
        <div className="auth-form-panel__inner">
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p className="auth-form-panel__description">{description}</p>
          {children}
          {footer ? <div className="auth-form-panel__footer">{footer}</div> : null}
        </div>
      </section>
    </main>
  );
}
