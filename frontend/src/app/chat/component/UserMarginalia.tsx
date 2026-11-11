import type { ReactNode } from "react";

import { useAuth } from "../../auth/AuthProvider";
import { useI18n } from "../../i18n";
import type { ChatAttachmentView } from "../types";
import { ChatImage } from "./ChatImage";

interface UserMarginaliaProps {
  readonly text: string;
  readonly attachments?: readonly ChatAttachmentView[];
  readonly createdAt?: string;
  readonly pending?: boolean;
  readonly action?: ReactNode;
}

/** The keeper's turn: a compact author line and an ink speech bubble. */
export function UserMarginalia({
  text,
  attachments = [],
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
      {attachments.length > 0 ? (
        <div className="chat-turn__attachments">
          {attachments.map((attachment) => (
            <ChatImage key={attachment.id} attachment={attachment} />
          ))}
        </div>
      ) : null}
      {text.trim().length > 0 ? (
        <div className="chat-turn__bubble">{text}</div>
      ) : null}
    </article>
  );
}
