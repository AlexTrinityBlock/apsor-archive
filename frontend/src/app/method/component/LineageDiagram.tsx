import { Badge } from "../../component/Badge";
import { Icon } from "../../component/Icon";

const VERSIONS = [
  { label: "v1", year: "2024", id: "file 08", state: "history" },
  { label: "v2", year: "2025", id: "file 11", state: "history" },
  { label: "v3", year: "2026", id: "file 12", state: "current" },
] as const;

/** Figure 02: a same-path upload grows a new version instead of overwriting. */
export function LineageDiagram() {
  return (
    <figure className="method-figure">
      <div className="lineage-diagram">
        <div className="lineage-diagram__path">
          <span className="figure-label">Same path, three editions</span>
          <code>/history/industry/automobiles/2026_automobile_history.md</code>
        </div>
        <div className="version-chain">
          {VERSIONS.map((version, index) => (
            <div className="version-chain__piece" key={version.label}>
              <div
                className={
                  version.state === "current"
                    ? "version-node is-current"
                    : "version-node is-history"
                }
              >
                <div className="version-node__top">
                  <span>{version.label}</span>
                  <Badge tone={version.state === "current" ? "moss" : "neutral"} dot>
                    {version.state}
                  </Badge>
                </div>
                <strong>{version.year}</strong>
                <span className="version-node__id">{version.id}</span>
                <span className="version-node__line" aria-hidden="true" />
              </div>
              {index < VERSIONS.length - 1 ? (
                <span className="version-chain__arrow" aria-hidden="true">
                  <Icon name="arrow-right" size={17} />
                </span>
              ) : null}
            </div>
          ))}
        </div>
        <div className="version-key">
          <span>
            <i className="legend-line legend-line--solid" aria-hidden="true" />
            Current chunks · default search
          </span>
          <span>
            <i className="legend-line legend-line--dashed" aria-hidden="true" />
            Superseded chunks · trace only
          </span>
        </div>
      </div>
      <figcaption>
        Figure 02 — Ids are never reused. The old file, tree node, and chunks stay
        addressable, but leave the default surface. History is opt-in.
      </figcaption>
    </figure>
  );
}
