import { pathSegments } from "../../../lib/format";
import { Icon } from "../../component/Icon";

interface LibraryBreadcrumbsProps {
  readonly path: string;
  readonly onNavigate: (path: string) => void;
}

/**
 * The compact archive-path trail. Every folder segment is a button that
 * updates the `path` query parameter; the current leaf stays a quiet marker.
 */
export function LibraryBreadcrumbs({ path, onNavigate }: LibraryBreadcrumbsProps) {
  const segments = pathSegments(path);

  return (
    <nav className="library-crumbs" aria-label="Breadcrumb">
      <ol>
        <li>
          <button
            type="button"
            className="library-crumb library-crumb--root"
            onClick={() => onNavigate("/")}
          >
            <Icon name="library" size={15} />
            <span>File library</span>
          </button>
        </li>
        {segments.map((segment, index) => {
          const target = `/${segments.slice(0, index + 1).join("/")}`;
          const isCurrent = index === segments.length - 1;
          return (
            <li key={target}>
              <span className="library-crumbs__sep" aria-hidden="true">
                <Icon name="chevron-right" size={11} />
              </span>
              {isCurrent ? (
                <span className="library-crumb is-current" aria-current="page">
                  {segment}
                </span>
              ) : (
                <button type="button" className="library-crumb" onClick={() => onNavigate(target)}>
                  {segment}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
