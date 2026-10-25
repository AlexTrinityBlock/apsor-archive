import type { ReactNode } from "react";

import { useAuth } from "../../auth/AuthProvider";
import { useI18n } from "../../i18n";

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
  const { user } = useAuth();
  const { t, formatRelative } = useI18n();
  const name = user?.display_name || user?.username || t("core.nav.owner");
  return (
    <article
      className={pending ? "chat-turn chat-turn--user is-pending" : "chat-turn chat-turn--user"}
    >
      <header className="chat-turn__author">
        <span className="chat-turn__mark" aria-hidden="true">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span>
          {pending ? t("chat.user.sending", { name }) : name}
        </span>
        {createdAt ? (
          <time dateTime={createdAt}>{formatRelative(createdAt)}</time>
        ) : (
          <span>{t("chat.user.now")}</span>
        )}
        {action}
      </header>
      <div className="chat-turn__bubble">{text}</div>
    </article>
  );
}
