import type { ReactNode } from "react";

import { TreeMark } from "../../component/TreeMark";
import { TreeRings } from "../../component/TreeRings";
import { useI18n } from "../../i18n";
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
  const { t } = useI18n();

  return (
    <main className="auth-screen">
      <div className="auth-screen__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>

      <div className="auth-shell">
        <section className="auth-aside" aria-label={t("core.auth.frame.asideAria")}>
          <div className="auth-aside__rings" aria-hidden="true">
            <TreeRings variant="quiet" />
          </div>

          <header className="auth-brand">
            <span className="auth-brand__seal">
              <TreeMark size={28} />
            </span>
            <span className="auth-brand__meta">
              <span className="auth-brand__name">{t("core.app.name")}</span>
              <span className="auth-brand__sub">{t("core.app.studio")}</span>
            </span>
          </header>

          <div className="auth-aside__copy">
            <p className="eyebrow">{t("core.auth.frame.asideEyebrow")}</p>
            <p className="auth-aside__headline">
              {t("core.auth.frame.asideHeadline")}
              <span>{t("core.auth.frame.asideHeadlineAccent")}</span>
            </p>
            <p>{t("core.auth.frame.asideDescription")}</p>
            <ul className="auth-aside__facts">
              <li>{t("core.auth.frame.localFirst")}</li>
              <li>{t("core.auth.frame.privateAccounts")}</li>
              <li>{t("core.auth.frame.noTelemetry")}</li>
            </ul>
          </div>

          <footer className="auth-aside__foot">
            <span>{t("core.auth.frame.footerProtocol")}</span>
            <span>{t("core.auth.frame.footerYear")}</span>
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
