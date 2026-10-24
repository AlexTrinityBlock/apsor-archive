import type { ReactNode } from "react";

import type { SettingsTone } from "./settings-utils";

interface StatusPillProps {
  readonly tone: SettingsTone;
  readonly children: ReactNode;
}

/** A compact diagnostics pill with a status dot and mono label. */
export function StatusPill({ tone, children }: StatusPillProps) {
  return (
    <span className={`status-pill status-pill--${tone}`}>
      <span className="status-pill__dot" aria-hidden="true" />
      {children}
    </span>
  );
}
