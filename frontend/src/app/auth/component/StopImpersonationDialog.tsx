import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { useScrollLock } from "../../hook/useScrollLock";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { useAuth } from "../AuthProvider";
import "../auth.css";

interface StopImpersonationDialogProps {
  readonly targetName: string;
  readonly targetUsername: string;
  readonly rootName: string;
  readonly onClose: () => void;
  readonly onStopped: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function initialsFor(name: string): string {
  return Array.from(name.trim()).slice(0, 2).join("").toUpperCase() || "?";
}

/**
 * Root re-authentication before returning from an impersonation session. The
 * impersonated account must not be able to take over root by clicking the
 * banner, so the fresh root session requires the root password.
 */
export function StopImpersonationDialog({
  targetName,
  targetUsername,
  rootName,
  onClose,
  onStopped,
}: StopImpersonationDialogProps) {
  const { t } = useI18n();
  const { stopImpersonation } = useAuth();
  const apiErrorMessage = useApiErrorMessage();
  const titleId = useId();
  const descriptionId = useId();
  const passwordId = useId();
  const passwordHintId = useId();
  const errorId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const onCloseRef = useRef(onClose);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    passwordRef.current?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) {
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
  }, [submitting]);

  const passwordDescription = error
    ? `${passwordHintId} ${errorId}`
    : passwordHintId;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setError(null);
    if (password.length === 0) {
      setError(t("core.impersonation.stop.passwordRequired"));
      passwordRef.current?.focus();
      return;
    }
    setSubmitting(true);
    try {
      await stopImpersonation(password);
      setPassword("");
      onStopped();
    } catch (caught) {
      // Never leave a submitted root password in the dialog after a failure;
      // the impersonated person may be the next person at this browser.
      setPassword("");
      setShowPassword(false);
      setError(apiErrorMessage(caught, "core.impersonation.stopError"));
      passwordRef.current?.focus();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting) {
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
        aria-busy={submitting}
        tabIndex={-1}
        className="modal-dialog modal-dialog--sm stop-impersonation"
      >
        <header className="modal-head stop-impersonation__head">
          <div className="stop-impersonation__heading">
            <p className="eyebrow">{t("core.impersonation.stop.eyebrow")}</p>
            <h2 className="modal-title" id={titleId}>
              {t("core.impersonation.stop.title")}
            </h2>
          </div>
          <button
            type="button"
            className="modal-btn-close"
            onClick={onClose}
            disabled={submitting}
            aria-label={t("core.common.close")}
          >
            <Icon name="close" size={18} />
          </button>
        </header>

        <div className="modal-body modal-body--plain stop-impersonation__body">
          <p className="stop-impersonation__description" id={descriptionId}>
            {t("core.impersonation.stop.description")}
          </p>

          <div className="stop-impersonation__context">
            <div className="stop-impersonation__target">
              <span className="stop-impersonation__avatar" aria-hidden="true">
                {initialsFor(targetName)}
              </span>
              <span className="stop-impersonation__target-copy">
                <span className="stop-impersonation__label">
                  {t("core.impersonation.viewingAs")}
                </span>
                <strong>{targetName}</strong>
                <span>@{targetUsername}</span>
              </span>
            </div>
            <p className="stop-impersonation__actor">
              <span>{t("core.impersonation.stop.actorLabel")}</span>
              <strong>{rootName}</strong>
            </p>
          </div>

          <form
            className="stop-impersonation__form"
            onSubmit={(event) => void handleSubmit(event)}
            noValidate
          >
            <div className="field">
              <label className="field-label" htmlFor={passwordId}>
                {t("core.impersonation.stop.passwordLabel")}
              </label>
              <div className="auth-password stop-impersonation__password">
                <input
                  ref={passwordRef}
                  className="input"
                  id={passwordId}
                  name="root-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setError(null);
                  }}
                  autoComplete="current-password"
                  maxLength={256}
                  required
                  disabled={submitting}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={passwordDescription}
                />
                <button
                  type="button"
                  className="auth-password__toggle"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={
                    showPassword
                      ? t("core.impersonation.stop.hidePassword")
                      : t("core.impersonation.stop.showPassword")
                  }
                  aria-pressed={showPassword}
                  aria-controls={passwordId}
                  disabled={submitting}
                >
                  {showPassword
                    ? t("core.impersonation.stop.hide")
                    : t("core.impersonation.stop.show")}
                </button>
              </div>
              <small className="field-help" id={passwordHintId}>
                {t("core.impersonation.stop.passwordHint")}
              </small>
            </div>

            {error ? (
              <p className="stop-impersonation__error" id={errorId} role="alert">
                <Icon name="info" size={15} />
                {error}
              </p>
            ) : null}

            <div className="stop-impersonation__actions">
              <Button
                type="button"
                variant="ghost"
                onClick={onClose}
                disabled={submitting}
              >
                {t("core.accounts.cancel")}
              </Button>
              <Button type="submit" variant="ink" disabled={submitting}>
                {submitting
                  ? t("core.impersonation.stop.submitting")
                  : t("core.impersonation.stop.submit")}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
