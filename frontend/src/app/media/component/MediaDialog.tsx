import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";

import { useScrollLock } from "../../hook/useScrollLock";
import { Icon } from "../../component/Icon";

interface MediaDialogProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly description?: ReactNode;
  readonly children: ReactNode;
  readonly onClose: () => void;
  readonly className?: string;
  readonly dismissible?: boolean;
  readonly wide?: boolean;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The media archive's modal shell. It closes on Escape or a click on the wash,
 * traps keyboard focus, and restores the trigger's focus when it unmounts.
 */
export function MediaDialog({
  eyebrow,
  title,
  description,
  children,
  onClose,
  className,
  dismissible = true,
  wide = false,
}: MediaDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    const initial =
      dialog?.querySelector<HTMLElement>("[data-autofocus]") ??
      dialog?.querySelector<HTMLElement>(FOCUSABLE) ??
      dialog;
    initial?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (dismissible) {
          event.preventDefault();
          onCloseRef.current();
        }
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.offsetParent !== null,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [dismissible]);

  return (
    <div
      className="media-dialog-layer"
      onMouseDown={(event) => {
        if (dismissible && event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={["media-dialog", wide ? "media-dialog--wide" : null, className]
          .filter(Boolean)
          .join(" ")}
      >
        <header className="media-dialog__head">
          <div className="media-dialog__heading">
            <p className="eyebrow">{eyebrow}</p>
            <h2 id={titleId}>{title}</h2>
            {description ? (
              <p id={descriptionId} className="media-dialog__description">
                {description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            className="media-dialog__close"
            onClick={onClose}
            aria-label="Close dialog"
            disabled={!dismissible}
          >
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="media-dialog__body">{children}</div>
      </div>
    </div>
  );
}
