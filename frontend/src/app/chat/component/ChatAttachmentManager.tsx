import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  getListAgentChatAttachmentsQueryKey,
  useDeleteAgentChatAttachment,
  useListAgentChatAttachments,
} from "../../generated-apis-types/agent/agent";
import type { AgentChatAttachmentSchema } from "../../generated-apis-types/schemas";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";
import { formatAttachmentBytes } from "../attachments";
import { ChatImage } from "./ChatImage";

interface ChatAttachmentManagerProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onDeleted?: (attachmentId: number) => void;
}

function attachmentView(attachment: AgentChatAttachmentSchema) {
  return {
    id: attachment.id,
    fileName: attachment.file_name,
    mimeType: attachment.mime_type,
    sizeBytes: attachment.size_bytes,
    width: attachment.width,
    height: attachment.height,
    contentUrl: attachment.content_url,
  };
}

/**
 * The account's temporary chat-image area.
 *
 * Images are uploaded before the message is sent, so this panel is also the
 * recovery path for a paste that was never submitted. Deleting an attached
 * image removes its object; the transcript then shows a placeholder.
 */
export function ChatAttachmentManager({
  open,
  onClose,
  onDeleted,
}: ChatAttachmentManagerProps) {
  const { t, formatRelative } = useI18n();
  const toast = useToast();
  const queryClient = useQueryClient();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const list = useListAgentChatAttachments(
    { limit: 100 },
    {
      query: {
        enabled: open,
        retry: false,
      },
    },
  );
  const remove = useDeleteAgentChatAttachment();

  useScrollLock(open);

  useEffect(() => {
    if (!open) {
      return;
    }
    closeRef.current?.focus();
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  const attachments = list.data?.resources ?? [];
  const deleting = remove.isPending;

  const deleteAttachment = async (attachmentId: number) => {
    try {
      await remove.mutateAsync({ attachmentId });
      setPendingDeleteId(null);
      onDeleted?.(attachmentId);
      await queryClient.invalidateQueries({
        queryKey: getListAgentChatAttachmentsQueryKey(),
      });
      toast.success(t("chat.attachments.deleted"));
    } catch {
      toast.error(t("chat.attachments.deleteFailed"));
    }
  };

  let body: ReactNode;
  if (list.isLoading) {
    body = (
      <div className="chat-attachment-manager__state" role="status">
        <Loader size={18} label={t("chat.attachments.loading")} />
        {t("chat.attachments.loading")}
      </div>
    );
  } else if (list.isError) {
    body = (
      <div className="chat-attachment-manager__state" role="alert">
        <p>{t("chat.attachments.loadFailed")}</p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => void list.refetch()}
        >
          {t("chat.attachments.retry")}
        </Button>
      </div>
    );
  } else if (attachments.length === 0) {
    body = (
      <div className="chat-attachment-manager__state">
        <Icon name="image" size={24} />
        <p>{t("chat.attachments.empty")}</p>
      </div>
    );
  } else {
    body = (
      <ul className="chat-attachment-manager__list">
        {attachments.map((attachment) => {
          const confirming = pendingDeleteId === attachment.id;
          const statusLabel =
            attachment.status === "attached"
              ? t("chat.attachments.attached")
              : t("chat.attachments.staged");
          const confirmLabel = deleting
            ? t("chat.attachments.deleting")
            : t("chat.attachments.confirmDelete");
          return (
            <li
              key={attachment.id}
              className="chat-attachment-manager__item"
            >
              <ChatImage attachment={attachmentView(attachment)} compact />
              <div className="chat-attachment-manager__meta">
                <strong>{attachment.file_name}</strong>
                <span>
                  {formatAttachmentBytes(attachment.size_bytes)} ·{" "}
                  {formatRelative(attachment.created_at)}
                </span>
                <span
                  className={`chat-attachment-manager__status chat-attachment-manager__status--${attachment.status}`}
                >
                  {statusLabel}
                </span>
              </div>
              {confirming ? (
                <div className="chat-attachment-manager__confirm">
                  <p>{t("chat.attachments.deleteWarning")}</p>
                  <div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => setPendingDeleteId(null)}
                      disabled={deleting}
                    >
                      {t("chat.attachments.cancel")}
                    </Button>
                    <Button
                      type="button"
                      variant="ink"
                      size="sm"
                      onClick={() => void deleteAttachment(attachment.id)}
                      disabled={deleting}
                    >
                      {confirmLabel}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setPendingDeleteId(attachment.id)}
                  aria-label={t("chat.attachments.deleteAria", {
                    name: attachment.file_name,
                  })}
                >
                  <Icon name="trash" size={12} />
                  {t("chat.attachments.delete")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  return createPortal(
    <div className="chat-modal" role="presentation">
      <button
        type="button"
        className="chat-modal__backdrop"
        aria-label={t("chat.attachments.close")}
        onClick={onClose}
      />
      <section
        className="chat-modal__panel chat-attachment-manager"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-attachment-manager-title"
      >
        <header className="chat-modal__head">
          <div>
            <p className="mono-label">{t("chat.attachments.eyebrow")}</p>
            <h2 id="chat-attachment-manager-title">
              {t("chat.attachments.title")}
            </h2>
            <p>{t("chat.attachments.detail")}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="chat-modal__close"
            onClick={onClose}
            aria-label={t("chat.attachments.close")}
            title={t("chat.attachments.close")}
          >
            <Icon name="close" size={16} />
          </button>
        </header>

        <div className="chat-attachment-manager__body">{body}</div>
      </section>
    </div>,
    document.body,
  );
}
