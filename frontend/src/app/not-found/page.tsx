import { useLocation } from "react-router-dom";

import { ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { TreeRings } from "../component/TreeRings";
import { useI18n } from "../i18n";
import "./not-found.css";

/** A quiet 404 that still belongs to the archive shell. */
export function NotFoundPage() {
  const location = useLocation();
  const { t } = useI18n();

  return (
    <div className="content-container content-container--reading not-found-page">
      <div className="not-found__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>

      <div className="not-found__content">
        <p className="eyebrow">{t("core.notFound.eyebrow")}</p>
        <h1 className="not-found__title">{t("core.notFound.title")}</h1>
        <p className="not-found__description">
          {t("core.notFound.description")}
        </p>
        <div className="not-found__actions">
          <ButtonLink to="/" variant="primary">
            {t("core.notFound.returnOverview")}
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
          <ButtonLink to="/search" variant="secondary">
            {t("core.notFound.searchArchive")}
          </ButtonLink>
        </div>
        <div className="not-found__code">
          <code>GET {location.pathname}</code>
          <span aria-hidden="true">→</span>
          <code>404 not_found</code>
        </div>
      </div>
    </div>
  );
}
