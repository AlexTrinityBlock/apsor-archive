import { useId, useMemo, useState } from "react";

import type {
  CompanionBondAdminSchema,
  CompanionUserFragmentSchema,
} from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import {
  constellationLines,
  countStates,
  layoutStars,
  timelineMarks,
  type FragmentLike,
} from "../constellation";

interface ConstellationTimelineProps {
  readonly bond: CompanionBondAdminSchema;
  readonly fragments: readonly CompanionUserFragmentSchema[];
  readonly familiarRuns: number;
  readonly rareRuns: number;
  readonly portrait: string | null;
  readonly onSelect: (key: string) => void;
}

const SIZE = 320;

/**
 * The account's memories as a sky: three rings (first, familiar, rare), lit
 * stars for told memories, dim stars for unlocked ones, and faint dots for
 * locked ones. Below it, a run axis shows tier unlocks and the next moment.
 */
export function ConstellationTimeline({
  bond,
  fragments,
  familiarRuns,
  rareRuns,
  portrait,
  onSelect,
}: ConstellationTimelineProps) {
  const { t, formatNumber } = useI18n();
  const titleId = useId();
  const [hovered, setHovered] = useState<string | null>(null);
  const stars = useMemo(
    () => layoutStars(fragments as readonly FragmentLike[], SIZE),
    [fragments],
  );
  const lines = useMemo(() => constellationLines(stars), [stars]);
  const counts = countStates(fragments as readonly FragmentLike[]);
  const timeline = timelineMarks({
    completedRuns: bond.completed_runs,
    familiarRuns,
    rareRuns,
    nextMomentIn: bond.next_story_moment_in_runs ?? null,
  });
  const hoveredFragment =
    fragments.find((fragment) => fragment.key === hovered) ?? null;

  return (
    <div className="ca-sky">
      <figure className="ca-sky__figure" aria-labelledby={titleId}>
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="ca-sky__svg"
          role="img"
          aria-label={t("companionAdmin.companion.sections.skyHint")}
        >
          {[0.36, 0.62, 0.86].map((ring) => (
            <circle
              key={ring}
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={(SIZE / 2) * ring}
              className="ca-sky__ring"
            />
          ))}
          {lines.map(([from, to]) => (
            <line
              key={`${from.key}-${to.key}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              className="ca-sky__line"
            />
          ))}
          {stars.map((star) => (
            <circle
              key={star.key}
              cx={star.x}
              cy={star.y}
              r={star.r}
              className={`ca-star ca-star--${star.state} ca-star--${star.origin}${
                star.hidden ? " ca-star--hidden" : ""
              }${hovered === star.key ? " is-hovered" : ""}`}
              tabIndex={0}
              role="button"
              aria-label={[
                star.key,
                t(`companionAdmin.fragments.states.${star.state}`),
              ].join(" · ")}
              onMouseEnter={() => setHovered(star.key)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(star.key)}
              onBlur={() => setHovered(null)}
              onClick={() => onSelect(star.key)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(star.key);
                }
              }}
            />
          ))}
        </svg>
        {portrait ? (
          <img
            className="ca-sky__portrait"
            src={portrait}
            alt=""
            width={72}
            height={72}
            loading="lazy"
            decoding="async"
            onError={(event) => {
              event.currentTarget.hidden = true;
            }}
          />
        ) : null}
        <figcaption id={titleId} className="ca-sky__caption">
          {hoveredFragment ? (
            <>
              <strong>{hoveredFragment.key}</strong>
              <span>{hoveredFragment.text.slice(0, 140)}…</span>
            </>
          ) : (
            <span>{t("companionAdmin.companion.sections.skyHint")}</span>
          )}
        </figcaption>
      </figure>

      <ul className="ca-sky__legend">
        <li>
          <span className="ca-dot ca-dot--told" aria-hidden="true" />
          {t("companionAdmin.companion.legend.told")} ·{" "}
          {formatNumber(counts.told)}
        </li>
        <li>
          <span className="ca-dot ca-dot--unlocked" aria-hidden="true" />
          {t("companionAdmin.companion.legend.unlocked")} ·{" "}
          {formatNumber(counts.unlocked)}
        </li>
        <li>
          <span className="ca-dot ca-dot--locked" aria-hidden="true" />
          {t("companionAdmin.companion.legend.locked")} ·{" "}
          {formatNumber(counts.locked)}
        </li>
      </ul>

      <div
        className="ca-timeline"
        aria-label={t("companionAdmin.companion.timeline.label")}
      >
        <div className="ca-timeline__track">
          <div
            className="ca-timeline__fill"
            style={{
              width: `${(timeline.marks.find((mark) => mark.kind === "now")?.at ?? 0) * 100}%`,
            }}
          />
          {timeline.marks.map((mark) => (
            <span
              key={mark.kind}
              className={`ca-timeline__mark ca-timeline__mark--${mark.kind}`}
              style={{ left: `${mark.at * 100}%` }}
            >
              <span className="ca-timeline__label">
                {t(`companionAdmin.companion.timeline.${mark.kind}`)}
                <small>
                  {t("companionAdmin.companion.timeline.runs", {
                    count: formatNumber(mark.run),
                  })}
                </small>
              </span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
