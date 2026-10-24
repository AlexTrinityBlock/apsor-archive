import { useLocation } from "react-router-dom";

import { ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { TreeRings } from "../component/TreeRings";
import "./not-found.css";

/** A quiet 404 that still belongs to the archive shell. */
export function NotFoundPage() {
  const location = useLocation();

  return (
    <div className="content-container content-container--reading not-found-page">
      <div className="not-found__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>

      <div className="not-found__content">
        <p className="eyebrow">Archive · 404</p>
        <h1 className="not-found__title">This page is not in the archive.</h1>
        <p className="not-found__description">
          The address may be mistyped, or the page has moved to another room.
          Nothing was deleted; the archive is still here.
        </p>
        <div className="not-found__actions">
          <ButtonLink to="/" variant="primary">
            Return to the overview
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
          <ButtonLink to="/search" variant="secondary">
            Search the archive
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
