import {
  useId,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent,
  type Ref,
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

/** Imperative focus control the page uses after send, new chat, or a suggestion. */
export interface ChatComposerHandle {
  /**
   * Move focus into the message box with the caret at the end. A programmatic
   * focus is skipped on coarse pointers so a phone keyboard does not pop up
   * after an action the reader did not aim at the composer.
   */
  readonly focus: (options?: { readonly programmatic?: boolean }) => void;
}

/** Why the composer is blocked, when it is blocked for a specific reason. */
export type ComposerBlockReason = "approval" | null;

export const COMPOSER_MAX_LENGTH = 32_000;
/** Show the character counter once the draft passes this share of the limit. */
const COUNTER_THRESHOLD = 0.85;

interface ChatComposerProps {
  readonly composerRef?: Ref<ChatComposerHandle>;
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
  readonly blockReason?: ComposerBlockReason;
  readonly onStop: () => void;
}

const MAX_HEIGHT = 220;

function isCoarsePointer(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(pointer: coarse)").matches
  );
}

/**
 * A sticky composer. A hardware keyboard keeps Enter-to-send and Shift+Enter
 * for a newline; touch-first phones and narrow windows use Enter as a newline
 * and submit only through the Send button. Ctrl/Cmd+Enter always sends, and
 * Escape stops a streaming answer.
 */
export function ChatComposer({
  composerRef,
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
  blockReason = null,
  onStop,
}: ChatComposerProps) {
  const inputId = useId();
  const hintId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { t, formatNumber } = useI18n();
  const mobileComposer = useMobileComposer();
  const uploading = attachments.some((item) => item.status === "uploading");
  const uploadFailed = attachments.some((item) => item.status === "error");
  const attachmentsReady = attachments.every((item) => item.status === "ready");
  const readyCount = attachments.filter((item) => item.status === "ready").length;
  const canSubmit =
    (value.trim().length > 0 || readyCount > 0) &&
    attachmentsReady &&
    !pending &&
    !disabled;

  // Layout effect: the measured height lands before paint, so a new line
  // never flashes at the old height for one frame.
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  useImperativeHandle(
    composerRef,
    () => ({
      focus: (options) => {
        const textarea = textareaRef.current;
        if (!textarea || (options?.programmatic && isCoarsePointer())) {
          return;
        }
        textarea.focus({ preventScroll: true });
        const end = textarea.value.length;
        textarea.setSelectionRange(end, end);
      },
    }),
    [],
  );

  const submit = () => {
    if (canSubmit) {
      onSubmit(value.trim());
      // Send disables itself; keep focus in the message box instead of <body>.
      textareaRef.current?.focus({ preventScroll: true });
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mobileComposer) {
      submit();
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape" && streaming) {
      event.preventDefault();
      event.stopPropagation();
      onStop();
      return;
    }
    if (
      event.key === "Enter" &&
      (event.ctrlKey || event.metaKey) &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      submit();
      return;
    }
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
  } else if (disabled && blockReason === "approval") {
    note = t("chat.composer.noteAwaitingApproval");
  } else if (disabled) {
    note = t("chat.composer.noteDisabled");
  } else if (uploadFailed) {
    note = t("chat.composer.noteAttachmentError");
  } else if (uploading) {
    note = t("chat.composer.noteUploading");
  }

  const showCounter = value.length >= COMPOSER_MAX_LENGTH * COUNTER_THRESHOLD;

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
            {attachments.map((item) => {
              const removingLabel =
                item.status === "uploading"
                  ? t("chat.attachments.cancelUploadAria", {
                      name: item.fileName,
                    })
                  : t("chat.attachments.remove");
              return (
                <div
                  key={item.key}
                  className={`chat-attachment-chip chat-attachment-chip--${item.status}`}
                  title={
                    item.status === "error" ? (item.error ?? undefined) : undefined
                  }
                >
                  {item.status === "ready" && item.attachment ? (
                    <ChatImage attachment={item.attachment} compact />
                  ) : (
                    <span className="chat-attachment-chip__state">
                      {item.status === "uploading" ? (
                        <span
                          className="chat-attachment-chip__progress"
                          role="progressbar"
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={item.progress}
                          aria-label={t("chat.attachments.progressAria", {
                            name: item.fileName,
                            percent: item.progress,
                          })}
                        >
                          {t("chat.attachments.progress", {
                            percent: item.progress,
                          })}
                        </span>
                      ) : (
                        <Icon name="info" size={14} />
                      )}
                    </span>
                  )}
                  {item.status === "uploading" ? (
                    <span
                      className="chat-attachment-chip__bar"
                      style={{ width: `${item.progress}%` }}
                      aria-hidden="true"
                    />
                  ) : null}
                  {item.status === "error" ? (
                    <span className="visually-hidden">
                      {t("chat.attachments.uploadFailed", {
                        name: item.fileName,
                      })}
                    </span>
                  ) : null}
                  <button
                    type="button"
                    className="chat-attachment-chip__remove"
                    onClick={() => onRemoveAttachment(item.key)}
                    aria-label={removingLabel}
                    title={removingLabel}
                  >
                    <Icon name="close" size={10} />
                  </button>
                </div>
              );
            })}
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
          maxLength={COMPOSER_MAX_LENGTH}
          autoComplete="off"
          enterKeyHint={mobileComposer ? "enter" : "send"}
          disabled={disabled}
          aria-describedby={hintId}
        />

        <div className="chat-composer__foot">
          <span className="chat-composer__note" id={hintId}>
            <span>
              {t(
                mobileComposer
                  ? "chat.composer.enterHintMobile"
                  : "chat.composer.enterHint",
              )}
              {streaming ? ` · ${t("chat.composer.stopHint")}` : null}
            </span>
            <span className="chat-composer__state" aria-live="polite">
              {note}
            </span>
            {showCounter ? (
              <span
                className={
                  value.length >= COMPOSER_MAX_LENGTH
                    ? "chat-composer__count is-full"
                    : "chat-composer__count"
                }
              >
                {t("chat.composer.charCount", {
                  count: formatNumber(value.length),
                  max: formatNumber(COMPOSER_MAX_LENGTH),
                })}
              </span>
            ) : null}
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
            {/* Stop swaps into the Send slot so the action row never shifts. */}
            {streaming ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="chat-composer__primary chat-composer__stop"
                onClick={onStop}
              >
                <Icon name="stop" size={13} />
                {t("chat.composer.stop")}
              </Button>
            ) : (
              <Button
                type="button"
                variant="ink"
                size="sm"
                className="chat-composer__primary"
                disabled={!canSubmit}
                aria-busy={pending}
                onClick={submit}
              >
                {pending ? (
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
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
