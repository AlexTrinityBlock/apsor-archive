import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { buttonClassName } from "../../component/Button";
import { useI18n } from "../../i18n";

interface LeaveRunDialogProps {
  readonly open: boolean;
  readonly onStay: () => void;
  readonly onLeave: () => void;
}

/**
 * Confirms leaving the chat while an answer is still streaming. Leaving
 * disconnects the stream, which the backend records as a stopped run, so the
 * reader decides explicitly. Focus starts on Stay, Tab is trapped between the
 * two actions, Escape stays, and focus returns to where it was.
 */
export function LeaveRunDialog({ open, onStay, onLeave }: LeaveRunDialogProps) {
  if (!open) {
    return null;
  }
  return <LeaveRunDialogContent onStay={onStay} onLeave={onLeave} />;
}

function LeaveRunDialogContent({
  onStay,
  onLeave,
}: Omit<LeaveRunDialogProps, "open">) {
  const { t } = useI18n();
  const titleId = useId();
  const bodyId = useId();
  const stayRef = useRef<HTMLButtonElement>(null);
  const leaveRef = useRef<HTMLButtonElement>(null);
  const onStayRef = useRef(onStay);

  useEffect(() => {
    onStayRef.current = onStay;
  }, [onStay]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    stayRef.current?.focus();
    return () => previous?.focus();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onStayRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      event.preventDefault();
      const next =
        document.activeElement === stayRef.current
          ? leaveRef.current
          : stayRef.current;
      next?.focus();
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, []);

  return createPortal(
    <div
      className="modal chat-leave-modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onStay();
        }
      }}
    >
      <div
        className="modal-dialog modal-dialog--sm"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
      >
        <header className="modal-head">
          <h2 id={titleId} className="modal-title">
            {t("chat.leaveGuard.title")}
          </h2>
        </header>
        <div className="modal-body">
          <p id={bodyId}>{t("chat.leaveGuard.body")}</p>
        </div>
        <div className="modal-actions">
          <button
            ref={leaveRef}
            type="button"
            className={buttonClassName({ variant: "secondary", size: "sm" })}
            onClick={onLeave}
          >
            {t("chat.leaveGuard.leave")}
          </button>
          <button
            ref={stayRef}
            type="button"
            className={buttonClassName({ variant: "ink", size: "sm" })}
            onClick={onStay}
          >
            {t("chat.leaveGuard.stay")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
