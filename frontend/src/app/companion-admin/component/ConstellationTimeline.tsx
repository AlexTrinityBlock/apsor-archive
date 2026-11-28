import { useId, useMemo, useState } from "react";

import type {
  CompanionBondAdminSchema,
  CompanionUserFragmentSchema,
} from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import {
  WEIGHT_ORDER,
  constellationLines,
  countTold,
  isTold,
  layoutStars,
  timelineMarks,
  weightOf,
  type FragmentLike,
} from "../constellation";

interface ConstellationTimelineProps {
  readonly bond: CompanionBondAdminSchema;
  readonly fragments: readonly CompanionUserFragmentSchema[];
  readonly portrait: string | null;
  readonly onSelect: (key: string) => void;
}

const SIZE = 320;

/**
 * Every memory as a star; nothing is locked. Rings and hue show its weight
 * (everyday, the past, close to the heart), brightness shows whether the
 * librarian has told it yet. Below, a run axis marks the first conversation,
 * the last and next story moments, and now.
 */
export function ConstellationTimeline({
  bond,
  fragments,
  portrait,
  onSelect,
}: ConstellationTimelineProps) {
  const { t, formatNumber } = useI18n();
  const titleId = useId();
  const [hovered, setHovered] = useState<string | null>(null);
  const items = fragments as readonly FragmentLike[];
  const stars = useMemo(() => layoutStars(items, SIZE), [items]);
  const lines = useMemo(() => constellationLines(stars), [stars]);
  const counts = countTold(items);
  const timeline = timelineMarks({
    completedRuns: bond.completed_runs,
    lastStoryRun: bond.last_story_run ?? null,
    nextMomentIn: bond.next_story_moment_in_runs ?? null,
  });
  const nowAt = timeline.marks.find((mark) => mark.kind === "now")?.at ?? 0;
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
          {[0.36, 0.62, 0.86].map((ring, index) => (
            <circle
              key={ring}
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={(SIZE / 2) * ring}
              className={`ca-sky__ring ca-sky__ring--${WEIGHT_ORDER[index]}`}
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
          {stars.map((star) => {
            const state = star.told ? "told" : "untold";
            const classes = [
              "ca-star",
              `ca-star--${state}`,
              `ca-star--${star.weight}`,
              `ca-star--${star.origin}`,
              star.hidden ? "ca-star--hidden" : "",
              hovered === star.key ? "is-hovered" : "",
            ];
            return (
              <circle
                key={star.key}
                cx={star.x}
                cy={star.y}
                r={star.r}
                className={classes.filter(Boolean).join(" ")}
                tabIndex={0}
                role="button"
                aria-label={[
                  star.key,
                  t(`companionAdmin.fragments.weights.${star.weight}`),
                  t(`companionAdmin.fragments.states.${state}`),
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
            );
          })}
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
              <strong>
                {hoveredFragment.key} ·{" "}
                {t(
                  `companionAdmin.fragments.weights.${weightOf(hoveredFragment as FragmentLike)}`,
                )}
                {isTold(hoveredFragment as FragmentLike)
                  ? ` · ${t("companionAdmin.fragments.states.told")}`
                  : ""}
              </strong>
              <span>{hoveredFragment.text.slice(0, 160)}…</span>
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
          <span className="ca-dot ca-dot--untold" aria-hidden="true" />
          {t("companionAdmin.companion.legend.untold")} ·{" "}
          {formatNumber(counts.untold)}
        </li>
        {WEIGHT_ORDER.map((weight) => (
          <li key={weight}>
            <span className={`ca-dot ca-dot--${weight}`} aria-hidden="true" />
            {t(`companionAdmin.fragments.weights.${weight}`)} ·{" "}
            {formatNumber(
              items.filter((item) => weightOf(item) === weight).length,
            )}
          </li>
        ))}
      </ul>

      <div
        className="ca-timeline"
        aria-label={t("companionAdmin.companion.timeline.label")}
      >
        <div className="ca-timeline__track">
          <div
            className="ca-timeline__fill"
            style={{ width: `${nowAt * 100}%` }}
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
