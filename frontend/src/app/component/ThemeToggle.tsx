import { useTheme } from "../hook/useTheme";
import { Icon } from "./Icon";

interface ThemeToggleProps {
  readonly compact?: boolean;
  readonly className?: string;
}

/** Switches between the paper archive and the night archive. */
export function ThemeToggle({ compact = false, className }: ThemeToggleProps) {
  const { isDark, toggle } = useTheme();
  const nextLabel = isDark ? "Switch to paper archive" : "Switch to night archive";

  return (
    <button
      type="button"
      className={["theme-toggle", compact ? "theme-toggle--compact" : null, className]
        .filter(Boolean)
        .join(" ")}
      onClick={toggle}
      aria-pressed={isDark}
      title={nextLabel}
    >
      <span className="theme-toggle__icon" aria-hidden="true">
        <Icon name={isDark ? "sun" : "moon"} size={17} />
      </span>
      {compact ? null : (
        <>
          <span className="theme-toggle__copy">
            <span className="theme-toggle__label">
              {isDark ? "Night archive" : "Paper archive"}
            </span>
            <span className="theme-toggle__hint">Click to switch</span>
          </span>
          <span className="theme-toggle__switch" aria-hidden="true">
            <span className="theme-toggle__knob" />
          </span>
        </>
      )}
    </button>
  );
}
