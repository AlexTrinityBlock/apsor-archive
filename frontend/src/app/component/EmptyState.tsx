import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

interface EmptyStateProps {
  readonly icon?: IconName;
  readonly eyebrow?: string;
  readonly title: string;
  readonly description: string;
  readonly endpoint?: string;
  readonly method?: "GET" | "POST";
  readonly aside?: ReactNode;
  readonly action?: ReactNode;
  readonly className?: string;
}

/**
 * The shared "this room is being wired" state for route placeholders.
 * It doubles as a general empty state for future search and library results.
 */
export function EmptyState({
  icon = "ring",
  eyebrow = "Reserved for the live archive",
  title,
  description,
  endpoint,
  method = "GET",
  aside,
  action,
  className,
}: EmptyStateProps) {
  return (
    <section className={["empty-state", className].filter(Boolean).join(" ")}>
      <div className="empty-state__rings" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="empty-state__stamp" aria-hidden="true">
        Awaiting wiring
      </div>
      <div className="empty-state__icon">
        <Icon name={icon} size={28} />
      </div>
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p className="empty-state__description">{description}</p>
      {endpoint ? (
        <div className="endpoint-label">
          <span>{method}</span>
          <code>{endpoint}</code>
        </div>
      ) : null}
      {aside ? <div className="empty-state__aside">{aside}</div> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </section>
  );
}
