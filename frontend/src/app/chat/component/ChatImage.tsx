import { useState, type CSSProperties } from "react";

import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";
import type { ChatAttachmentView } from "../types";

const MAX_EDGE = 240;

/**
 * Reserve the rendered box before the image loads: the stored pixel size is
 * scaled into the 240px frame so the transcript does not jump on load.
 */
function reservedStyle(width: number, height: number): CSSProperties | undefined {
  if (width <= 0 || height <= 0) {
    return undefined;
  }
  const scale = Math.min(1, MAX_EDGE / width, MAX_EDGE / height);
  return {
    width: `min(${Math.round(width * scale)}px, 100%)`,
    aspectRatio: `${width} / ${height}`,
  };
}

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
        style={
          compact
            ? undefined
            : reservedStyle(attachment.width, attachment.height)
        }
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
      />
    </a>
  );
}
