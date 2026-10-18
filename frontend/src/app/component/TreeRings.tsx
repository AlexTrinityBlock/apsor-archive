import { useId } from "react";

const RING_RADII = [40, 58, 78, 97, 118, 140, 163, 186, 211, 236, 260, 286, 311, 335];

interface TreeRingsProps {
  readonly variant?: "hero" | "cta" | "quiet";
  readonly className?: string;
}

/**
 * Decorative cross-section of a tree: concentric rings, a circular label, and
 * a slow rotation. Each ring draws on mount. Reduced-motion users see the
 * finished drawing immediately.
 */
export function TreeRings({ variant = "hero", className }: TreeRingsProps) {
  const rawId = useId();
  const labelId = `rings-${rawId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const classes = ["tree-rings", `tree-rings--${variant}`, className].filter(Boolean).join(" ");

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 720 720"
      fill="none"
      className={classes}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <path id={labelId} d="M360 64a296 296 0 1 1-.1 0" />
      </defs>
      <g className="tree-rings__spin">
        {RING_RADII.map((radius, index) => {
          const isAccent = index === 7 || index === 10;
          return (
            <circle
              key={radius}
              cx="360"
              cy="360"
              r={radius}
              pathLength={1}
              className={isAccent ? "tree-rings__ring is-accent" : "tree-rings__ring"}
              style={{ animationDelay: `${120 + index * 65}ms` }}
              stroke="currentColor"
              strokeWidth={isAccent ? 1.35 : 0.8}
              strokeOpacity={0.18 + index * 0.028}
              strokeDasharray={isAccent ? "2 7" : undefined}
            />
          );
        })}
        <path
          className="tree-rings__scar"
          d="M360 25c-17 88 26 138-8 222-25 62 22 95-2 164-17 49 2 100 10 145"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeOpacity=".22"
        />
        <circle cx="360" cy="360" r="3.2" fill="currentColor" fillOpacity=".55" />
      </g>
      {variant === "hero" ? (
        <text className="tree-rings__lettering" fill="currentColor">
          <textPath href={`#${labelId}`} startOffset="2%">
            DENDROMATRIX · ANNUAL RING ARCHIVE · LOCAL-FIRST · SIX RETRIEVAL TOOLS ·
          </textPath>
        </text>
      ) : null}
    </svg>
  );
}
