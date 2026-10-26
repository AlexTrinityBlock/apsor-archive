import { useEffect, useId, useRef } from "react";

import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";
import { useAuth } from "../AuthProvider";
import { ChangePasswordForm } from "./ChangePasswordForm";
import "../auth.css";

interface ChangePasswordDialogProps {
  readonly onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Voluntary password change opened from the rail account card. The forced
 * first-login change stays on the full-screen AuthGate so no archive surface is
 * visible until the temporary password is replaced.
 */
export function ChangePasswordDialog({ onClose }: ChangePasswordDialogProps) {
  const { t } = useI18n();
  const { user } = useAuth();
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
      dialog?.querySelector<HTMLElement>(
        'input[name="current-password"]',
      ) ??
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
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="modal-dialog modal-dialog--sm change-password-dialog"
      >
        <header className="modal-head">
          <div>
            <p className="eyebrow">{t("core.auth.changePassword.eyebrow")}</p>
            <h2 className="modal-title" id={titleId}>
              {t("core.auth.changePassword.title")}
            </h2>
          </div>
          <button
            type="button"
            className="modal-btn-close"
            onClick={onClose}
            aria-label={t("core.common.close")}
          >
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="modal-body modal-body--plain">
          <div className="change-password-dialog__identity">
            <span className="change-password-dialog__mark" aria-hidden="true">
              {(user?.display_name || user?.username || "?").slice(0, 2).toUpperCase()}
            </span>
            <span>
              <strong>{user?.display_name || user?.username}</strong>
              {user ? <span>@{user.username}</span> : null}
            </span>
          </div>
          <p className="change-password-dialog__description" id={descriptionId}>
            {t("core.auth.changePassword.description")}
          </p>
          <ChangePasswordForm onSuccess={onClose} />
        </div>
      </div>
    </div>
  );
}
