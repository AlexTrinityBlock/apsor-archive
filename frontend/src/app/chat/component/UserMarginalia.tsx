import { formatTime } from "../../../lib/format";

interface UserMarginaliaProps {
  readonly text: string;
  readonly createdAt?: string;
  readonly pending?: boolean;
}

/** The keeper's side of the desk: a pencil note in the margin. */
export function UserMarginalia({
  text,
  createdAt,
  pending = false,
}: UserMarginaliaProps) {
  return (
    <article className={pending ? "chat-user is-pending" : "chat-user"}>
      <header className="chat-user__head">
        <span className="chat-user__mark" aria-hidden="true">
          K
        </span>
        <span className="chat-user__label">
          {pending ? "Sending · keeper" : "Marginalia · keeper"}
        </span>
        {createdAt ? (
          <time className="chat-user__time" dateTime={createdAt}>
            {formatTime(createdAt)}
          </time>
        ) : (
          <span className="chat-user__time">now</span>
        )}
      </header>
      <p className="chat-user__text">{text}</p>
    </article>
  );
}
