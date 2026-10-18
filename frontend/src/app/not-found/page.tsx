import { ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { TreeMark } from "../component/TreeMark";
import { TreeRings } from "../component/TreeRings";

/** A quiet 404 that still belongs to the archive. */
export function NotFoundPage() {
  return (
    <div className="page not-found-page">
      <div className="not-found__rings" aria-hidden="true">
        <TreeRings variant="quiet" />
      </div>
      <div className="not-found__content reveal reveal-1">
        <span className="not-found__mark">
          <TreeMark size={54} />
        </span>
        <p className="eyebrow">Archive · 404</p>
        <h1>
          This branch does not exist.
        </h1>
        <p>
          The path may have been mistyped, or the page has not been pressed into the
          archive yet. The rings are still here.
        </p>
        <div className="not-found__actions">
          <ButtonLink to="/" variant="ink">
            Return to the overview
            <Icon name="arrow-right" size={15} />
          </ButtonLink>
          <ButtonLink to="/search" variant="ghost">
            Search instead
          </ButtonLink>
        </div>
        <div className="not-found__code">
          <code>GET /this-path</code>
          <span aria-hidden="true">→</span>
          <code>404 not_found</code>
        </div>
      </div>
    </div>
  );
}
