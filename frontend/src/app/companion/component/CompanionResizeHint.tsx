import { useI18n } from "../../i18n";

interface CompanionResizeHintProps {
  readonly onDismiss: () => void;
}

function touchOnly(): boolean {
  try {
    return window.matchMedia("(hover: none)").matches;
  } catch {
    return false;
  }
}

/** One-time coach bubble that teaches the resize gestures. */
export function CompanionResizeHint({ onDismiss }: CompanionResizeHintProps) {
  const { t } = useI18n();
  const key = touchOnly()
    ? "companion.overlay.resize.coachTouch"
    : "companion.overlay.resize.coach";
  return (
    <div className="companion-coach" role="note">
      <p>{t(key)}</p>
      <button
        type="button"
        className="companion-coach__dismiss"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={onDismiss}
      >
        {t("companion.overlay.resize.coachDismiss")}
      </button>
    </div>
  );
}
