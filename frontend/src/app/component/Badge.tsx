import type { ReactNode } from "react";

import type { BadgeTone } from "../type/ui";

interface BadgeProps {
  readonly children: ReactNode;
  readonly tone?: BadgeTone;
  readonly dot?: boolean;
  readonly className?: string;
}

/** A small mono label for status, tool names, and archive metadata. */
export function Badge({ children, tone = "neutral", dot = false, className }: BadgeProps) {
  return (
    <span className={["badge", `badge--${tone}`, className].filter(Boolean).join(" ")}>
      {dot ? <span className="badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
