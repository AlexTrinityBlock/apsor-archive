import { Icon } from "../../component/Icon";
import { useI18n } from "../../i18n";

interface JumpToLatestProps {
  /** Shown only while the reader has scrolled away from the live tail. */
  readonly visible: boolean;
  /** New content arrived below since the reader scrolled away. */
  readonly hasNewActivity: boolean;
  readonly onJump: () => void;
}

/** Floating pill above the composer that re-attaches the transcript to its tail. */
export function JumpToLatest({ visible, hasNewActivity, onJump }: JumpToLatestProps) {
  const { t } = useI18n();
  if (!visible) {
    return null;
  }
  return (
    <button
      type="button"
      className={
        hasNewActivity ? "chat-jump-latest has-activity" : "chat-jump-latest"
      }
      onClick={onJump}
    >
      <Icon name="arrow-down" size={13} />
      {t("chat.scroll.jumpToLatest")}
      {hasNewActivity ? (
        <span className="chat-jump-latest__dot">
          <span className="visually-hidden">{t("chat.scroll.newActivity")}</span>
        </span>
      ) : null}
    </button>
  );
}
