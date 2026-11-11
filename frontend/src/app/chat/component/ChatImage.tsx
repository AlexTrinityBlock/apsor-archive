import { useState } from "react";

import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { ChatAttachmentView } from "../types";

interface ChatImageProps {
  readonly attachment: ChatAttachmentView;
  readonly compact?: boolean;
}

/**
 * One temporary chat image. A deleted object is a valid state: the transcript
 * keeps the message, but the image is replaced with an honest placeholder.
 */
export function ChatImage({ attachment, compact = false }: ChatImageProps) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  const className = compact ? "chat-image chat-image--compact" : "chat-image";

  if (failed) {
    return (
      <span className={`${className} chat-image--missing`} role="img">
        <Icon name="image" size={compact ? 16 : 22} />
        <span>{t("chat.attachments.unavailable")}</span>
      </span>
    );
  }

  return (
    <a
      className={className}
      href={attachment.contentUrl}
      target="_blank"
      rel="noreferrer"
      title={attachment.fileName}
    >
      <img
        src={attachment.contentUrl}
        alt={attachment.fileName}
        width={attachment.width}
        height={attachment.height}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
      />
    </a>
  );
}
