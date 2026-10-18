import { Badge } from "../../component/Badge";

const ANCHORS = [
  { fraction: "0.00", date: "01 Jun", event: "memory:940", tone: "moss" },
  { fraction: "0.25", date: "08 Jun", event: "file:12 v3", tone: "ochre" },
  { fraction: "0.50", date: "15 Jun", event: "summary:96", tone: "vermilion" },
  { fraction: "0.75", date: "23 Jun", event: "memory:997", tone: "moss" },
  { fraction: "1.00", date: "30 Jun", event: "memory:1015", tone: "moss" },
] as const;

/** Figure 04: five anchors, nearest events, and an honest count of the gaps. */
export function TimelineSamplingDiagram() {
  return (
    <figure className="method-figure">
      <div className="sampling-diagram">
        <div className="sampling-diagram__head">
          <div>
            <span className="figure-label">Range</span>
            <strong>June 2026</strong>
          </div>
          <div className="sampling-diagram__head-meta">
            <span>5 anchors</span>
            <span aria-hidden="true">/</span>
            <span>3 types</span>
            <span aria-hidden="true">/</span>
            <span>day_range 30</span>
          </div>
        </div>

        <div className="sampling-scroll" tabIndex={0} aria-label="Scrollable timeline sampling diagram">
          <div className="sampling-track">
            <div className="sampling-track__line" aria-hidden="true" />
            {ANCHORS.map((anchor) => (
              <div
                className={`sampling-anchor is-${anchor.tone}`}
                key={anchor.fraction}
              >
                <span className="sampling-anchor__fraction">{anchor.fraction}</span>
                <span className="sampling-anchor__stem" aria-hidden="true" />
                <span className="sampling-anchor__dot" aria-hidden="true" />
                <span className="sampling-anchor__date">{anchor.date}</span>
                <Badge tone={anchor.tone}>{anchor.event}</Badge>
              </div>
            ))}
          </div>
        </div>

        <div className="sampling-skips">
          <span className="figure-label">Skipped between anchors</span>
          <div>
            <span>9 memories</span>
            <span>2 files</span>
            <span>1 summary</span>
          </div>
        </div>

        <div
          className="sampling-density"
          role="img"
          aria-label="Illustrative daily density bars"
        >
          {[24, 38, 18, 56, 44, 30, 68, 42, 26, 60, 36, 48, 22, 52, 40, 64, 30, 46].map(
            (height, index) => (
              <span key={`${height}-${index}`} style={{ height: `${height}%` }} />
            ),
          )}
        </div>
      </div>
      <figcaption>
        Figure 04 — Sparse timeline sampling. Five anchors per kind choose the
        nearest unseen events; <code>skips</code> makes the omissions countable.
      </figcaption>
    </figure>
  );
}
