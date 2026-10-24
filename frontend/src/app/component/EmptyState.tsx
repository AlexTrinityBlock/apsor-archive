import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";
import "./shared.css";

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
 * The shared empty state for shelves, searches, and first-run surfaces. The
 * endpoint and method props stay on the API for existing call sites, but the
 * surface is written for readers rather than for wiring notes.
 */
export function EmptyState({
  icon = "ring",
  eyebrow,
  title,
  description,
  aside,
  action,
  className,
}: EmptyStateProps) {
  return (
    <section className={["empty-state", className].filter(Boolean).join(" ")}>
      <div className="empty-state__icon">
        <Icon name={icon} size={28} />
      </div>
      {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
      <h2 className="empty-state__title">{title}</h2>
      <p className="empty-state__description">{description}</p>
      {aside ? <div className="empty-state__aside">{aside}</div> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </section>
  );
}
