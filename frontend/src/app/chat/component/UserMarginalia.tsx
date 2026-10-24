import type { ReactNode } from "react";

import { formatTime } from "../../../lib/format";

interface UserMarginaliaProps {
  readonly text: string;
  readonly createdAt?: string;
  readonly pending?: boolean;
  readonly action?: ReactNode;
}

/** The keeper's turn: a compact author line and an ink speech bubble. */
export function UserMarginalia({
  text,
  createdAt,
  pending = false,
  action,
}: UserMarginaliaProps) {
  return (
    <article
      className={pending ? "chat-turn chat-turn--user is-pending" : "chat-turn chat-turn--user"}
    >
      <header className="chat-turn__author">
        <span className="chat-turn__mark" aria-hidden="true">
          K
        </span>
        <span>{pending ? "Keeper · sending" : "Keeper"}</span>
        {createdAt ? (
          <time dateTime={createdAt}>{formatTime(createdAt)}</time>
        ) : (
          <span>now</span>
        )}
        {action}
      </header>
      <div className="chat-turn__bubble">{text}</div>
    </article>
  );
}
