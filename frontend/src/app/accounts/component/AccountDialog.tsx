import { useEffect, useId, useRef, type ReactNode } from "react";

import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";

interface AccountDialogProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly description?: ReactNode;
  readonly children: ReactNode;
  readonly actions: ReactNode;
  readonly onClose: () => void;
  readonly busy?: boolean;
  readonly size?: "sm" | "md";
  readonly dismissible?: boolean;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The accounts workspace modal: focus trapped, Escape and backdrop aware, and
 * blocked while a mutation is in flight. The close button is hidden for a
 * non-dismissible one-time secret.
 */
export function AccountDialog({
  eyebrow,
  title,
  description,
  children,
  actions,
  onClose,
  busy = false,
  size = "sm",
  dismissible = true,
}: AccountDialogProps) {
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
      if (event.key === "Escape" && dismissible && !busy) {
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
  }, [busy, dismissible]);

  return (
    <div
      className="modal"
      onMouseDown={(event) => {
        if (
          event.target === event.currentTarget &&
          dismissible &&
          !busy
        ) {
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
        aria-busy={busy}
        tabIndex={-1}
        className={`modal-dialog modal-dialog--${size} accounts-dialog`}
      >
        <header className="modal-head accounts-dialog__head">
          <div className="accounts-dialog__heading">
            <p className="eyebrow">{eyebrow}</p>
            <h2 className="modal-title" id={titleId}>
              {title}
            </h2>
          </div>
          {dismissible ? (
            <button
              type="button"
              className="modal-btn-close"
              onClick={onClose}
              disabled={busy}
              aria-label={t("core.common.close")}
            >
              <Icon name="close" size={18} />
            </button>
          ) : null}
        </header>
        <div className="modal-body modal-body--plain accounts-dialog__body">
          {description ? (
            <p className="accounts-dialog__description" id={descriptionId}>
              {description}
            </p>
          ) : null}
          {children}
        </div>
        <footer className="modal-actions accounts-dialog__actions">
          {actions}
        </footer>
      </div>
    </div>
  );
}
