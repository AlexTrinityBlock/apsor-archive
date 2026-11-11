import {
  useEffect,
  useId,
  useRef,
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useI18n } from "../../i18n";
import {
  clipboardImageFiles,
  MAX_CHAT_IMAGES_PER_MESSAGE,
  type ComposerAttachment,
} from "../attachments";
import { useMobileComposer } from "../hook/useMobileComposer";
import { ChatImage } from "./ChatImage";

interface ChatComposerProps {
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly attachments: readonly ComposerAttachment[];
  readonly onAddImages: (files: File[]) => void;
  readonly onRemoveAttachment: (key: string) => void;
  readonly onManageAttachments: () => void;
  readonly pending: boolean;
  readonly streaming: boolean;
  readonly disabled?: boolean;
  readonly onStop: () => void;
}

const MAX_HEIGHT = 220;

/**
 * A sticky composer. A hardware keyboard keeps Enter-to-send and Shift+Enter
 * for a newline; touch-first phones and narrow windows use Enter as a newline
 * and submit only through the Send button.
 */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  attachments,
  onAddImages,
  onRemoveAttachment,
  onManageAttachments,
  pending,
  streaming,
  disabled = false,
  onStop,
}: ChatComposerProps) {
  const inputId = useId();
  const hintId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { t } = useI18n();
  const mobileComposer = useMobileComposer();
  const uploading = attachments.some((item) => item.status === "uploading");
  const readyCount = attachments.filter((item) => item.status === "ready").length;
  const canSubmit =
    (value.trim().length > 0 || readyCount > 0) &&
    !uploading &&
    !pending &&
    !disabled;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const submit = () => {
    if (canSubmit) {
      onSubmit(value.trim());
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mobileComposer) {
      submit();
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    ) {
      return;
    }
    // On touch-first layouts Enter is a normal newline. The Send button is the
    // only submit affordance, so mobile keyboards can compose multiple lines.
    if (mobileComposer) {
      return;
    }
    event.preventDefault();
    submit();
  };

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = clipboardImageFiles(event.clipboardData);
    if (files.length === 0) {
      return;
    }
    event.preventDefault();
    onAddImages(files);
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length > 0) {
      onAddImages(files);
    }
  };

  let note = t("chat.composer.note");
  if (streaming) {
    note = t("chat.composer.noteStreaming");
  } else if (disabled) {
    note = t("chat.composer.noteDisabled");
  }

  return (
    <form
      className="chat-composer"
      onSubmit={handleSubmit}
      aria-label={t("chat.composer.formAria")}
    >
      <div className="chat-composer__box">
        <label className="visually-hidden" htmlFor={inputId}>
          {t("chat.composer.message")}
        </label>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          hidden
          onChange={handleFileChange}
        />
        {attachments.length > 0 ? (
          <div className="chat-composer__attachments">
            {attachments.map((item) => (
              <div
                key={item.key}
                className={`chat-attachment-chip chat-attachment-chip--${item.status}`}
              >
                {item.status === "ready" && item.attachment ? (
                  <ChatImage attachment={item.attachment} compact />
                ) : (
                  <span className="chat-attachment-chip__state">
                    {item.status === "uploading" ? (
                      <Loader size={14} label={t("chat.attachments.uploading")} />
                    ) : (
                      <Icon name="info" size={14} />
                    )}
                  </span>
                )}
                <button
                  type="button"
                  className="chat-attachment-chip__remove"
                  onClick={() => onRemoveAttachment(item.key)}
                  aria-label={t("chat.attachments.remove")}
                  title={t("chat.attachments.remove")}
                >
                  <Icon name="close" size={10} />
                </button>
              </div>
            ))}
          </div>
        ) : null}
        <textarea
          ref={textareaRef}
          id={inputId}
          name="message"
          className="chat-composer__input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={t("chat.composer.placeholder")}
          rows={2}
          maxLength={32000}
          autoComplete="off"
          enterKeyHint={mobileComposer ? "enter" : "send"}
          disabled={disabled}
          aria-describedby={hintId}
          aria-busy={pending}
        />

        <div className="chat-composer__foot">
          <span className="chat-composer__note" id={hintId}>
            <span>
              {t(
                mobileComposer
                  ? "chat.composer.enterHintMobile"
                  : "chat.composer.enterHint",
              )}
            </span>
            <span className="chat-composer__state">{note}</span>
          </span>

          <div className="chat-composer__actions">
            <button
              type="button"
              className="chat-icon-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={
                disabled ||
                attachments.length >= MAX_CHAT_IMAGES_PER_MESSAGE
              }
              aria-label={t("chat.attachments.add")}
              title={t("chat.attachments.add")}
            >
              <Icon name="image" size={14} />
            </button>
            <button
              type="button"
              className="chat-icon-btn"
              onClick={onManageAttachments}
              aria-label={t("chat.attachments.manage")}
              title={t("chat.attachments.manage")}
            >
              <Icon name="folder" size={14} />
            </button>
            {streaming ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="chat-composer__stop"
                onClick={onStop}
              >
                <Icon name="stop" size={13} />
                {t("chat.composer.stop")}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ink"
              size="sm"
              disabled={!canSubmit}
              aria-busy={pending}
              onClick={submit}
            >
              {pending && !streaming ? (
                <>
                  <Loader size={14} label={t("chat.composer.openingLabel")} />
                  {t("chat.composer.opening")}
                </>
              ) : (
                <>
                  <span>{t("chat.composer.send")}</span>
                  <Icon name="send" size={14} />
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </form>
  );
}
