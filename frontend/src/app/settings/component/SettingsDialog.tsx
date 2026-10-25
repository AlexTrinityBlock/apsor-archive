import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";

import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";

interface SettingsDialogProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly description?: ReactNode;
  readonly children: ReactNode;
  readonly actions: ReactNode;
  readonly onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A quiet confirmation modal for maintenance actions. It closes on Escape or a
 * click on the wash, keeps focus inside, and restores the trigger on unmount.
 */
export function SettingsDialog({
  eyebrow,
  title,
  description,
  children,
  actions,
  onClose,
}: SettingsDialogProps) {
  const { t } = useI18n();
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
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
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null);
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
  }, []);

  return (
    <div
      className="modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
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
        className="modal-dialog modal-dialog--sm"
      >
        <header className="modal-head">
          <div className="settings-dialog__heading">
            <p className="eyebrow">{eyebrow}</p>
            <h2 className="modal-title" id={titleId}>
              {title}
            </h2>
          </div>
          <button
            type="button"
            className="modal-btn-close"
            onClick={onClose}
            aria-label={t("settings.common.closeDialog")}
          >
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="modal-body modal-body--plain">
          {description ? (
            <p className="settings-dialog__description" id={descriptionId}>
              {description}
            </p>
          ) : null}
          {children}
        </div>
        <footer className="modal-actions">{actions}</footer>
      </div>
    </div>
  );
}
