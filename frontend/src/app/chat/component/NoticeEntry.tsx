import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { noticeText } from "../types";

/** A display-only notice from the application, not the model. */
export function NoticeEntry({ entry }: { readonly entry: AgentEntrySchema }) {
  return (
    <aside className="chat-notice">
      <Icon name="info" size={15} />
      <p>{noticeText(entry)}</p>
      <span className="chat-notice__entry">#{entry.id}</span>
    </aside>
  );
}
