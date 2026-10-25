import { Icon } from "../../component/Icon";
import type { AgentEntrySchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import { noticeText } from "../types";

/** A display-only notice from the application, not the model. */
export function NoticeEntry({ entry }: { readonly entry: AgentEntrySchema }) {
  const { t } = useI18n();
  return (
    <aside className="chat-notice">
      <Icon name="info" size={15} />
      <p>{noticeText(entry, t("chat.notice.fallback"))}</p>
      <span className="chat-notice__entry">#{entry.id}</span>
    </aside>
  );
}
