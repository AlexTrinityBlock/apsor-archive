import { Badge } from "../../component/Badge";

/** Figure 01: the two provenance shapes, side by side. */
export function FileVsMemoryDiagram() {
  return (
    <figure className="method-figure">
      <div className="library-pair">
        <div className="library-pane library-pane--file">
          <header className="library-pane__head">
            <div>
              <span className="figure-label">File library</span>
              <h3>Known by its path</h3>
            </div>
            <Badge tone="moss">By path</Badge>
          </header>
          <div className="mini-tree" aria-label="Example file hierarchy">
            <div className="mini-tree__row depth-0">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">/history</span>
              <span className="mini-tree__kind">folder</span>
            </div>
            <div className="mini-tree__row depth-1">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">/industry</span>
              <span className="mini-tree__kind">folder</span>
            </div>
            <div className="mini-tree__row depth-2">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">/automobiles</span>
              <span className="mini-tree__kind">folder</span>
            </div>
            <div className="mini-tree__row depth-3 is-current">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">2026_automobile_history.md</span>
              <span className="mini-tree__kind">v3</span>
            </div>
            <div className="mini-tree__row depth-3 is-current">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">2024_ev_industry.pdf</span>
              <span className="mini-tree__kind">v1</span>
            </div>
            <div className="mini-tree__row depth-3 is-history">
              <span className="mini-tree__guide" aria-hidden="true" />
              <span className="mini-tree__name">2022_automobile_annual.md</span>
              <span className="mini-tree__kind">v2</span>
            </div>
          </div>
          <footer className="library-pane__foot">
            <span>Soft delete</span>
            <span aria-hidden="true">/</span>
            <span>Versions branch</span>
          </footer>
        </div>

        <div className="library-pane library-pane--memory">
          <header className="library-pane__head">
            <div>
              <span className="figure-label">Memory library</span>
              <h3>Known by its moment</h3>
            </div>
            <Badge tone="ochre">By time</Badge>
          </header>
          <div className="mini-axis" aria-label="Example memory timeline">
            <div className="mini-axis__line" aria-hidden="true" />
            <div className="mini-axis__event is-active">
              <span className="mini-axis__dot" aria-hidden="true" />
              <time>01 Jun</time>
              <span className="mini-axis__copy">The archive is the index.</span>
              <span className="mini-axis__id">memory:940</span>
            </div>
            <div className="mini-axis__event is-deprecated">
              <span className="mini-axis__dot" aria-hidden="true" />
              <time>16 Oct</time>
              <span className="mini-axis__copy">Paths are arguments about place.</span>
              <span className="mini-axis__id">memory:997</span>
            </div>
            <div className="mini-axis__event is-active">
              <span className="mini-axis__dot" aria-hidden="true" />
              <time>18 Oct</time>
              <span className="mini-axis__copy">Superseded, never erased.</span>
              <span className="mini-axis__id">memory:1015</span>
            </div>
          </div>
          <footer className="library-pane__foot">
            <span>Supersede chain</span>
            <span aria-hidden="true">/</span>
            <span>Trace stays open</span>
          </footer>
        </div>
      </div>
      <figcaption>
        Figure 01 — Two shapes of provenance. A path answers <em>where</em>; a
        timestamp answers <em>when</em>. The archive indexes both.
      </figcaption>
    </figure>
  );
}
