import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useI18n } from "../i18n";
import { Icon, type IconName } from "./Icon";

type ToastTone = "success" | "error" | "info";

const TOAST_ICONS: Record<ToastTone, IconName> = {
  success: "check",
  error: "info",
  info: "quote",
};

interface ToastItem {
  readonly id: number;
  readonly tone: ToastTone;
  readonly message: string;
}

interface ToastValue {
  readonly success: (message: string) => void;
  readonly error: (message: string) => void;
  readonly info: (message: string) => void;
}

const ToastContext = createContext<ToastValue | null>(null);
const LIFETIME_MS = 4500;

/** Non-modal confirmations for actions that should not interrupt reading. */
export function ToastProvider({ children }: { readonly children: ReactNode }) {
  const [toasts, setToasts] = useState<readonly ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback((tone: ToastTone, message: string) => {
    const id = nextId.current;
    nextId.current += 1;
    setToasts((current) => [...current, { id, tone, message }]);
  }, []);

  const value = useMemo<ToastValue>(
    () => ({
      success: (message) => push("success", message),
      error: (message) => push("error", message),
      info: (message) => push("info", message),
    }),
    [push],
  );

  return (
    <ToastContext value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <ToastNote key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext>
  );
}

function ToastNote({
  toast,
  onDismiss,
}: {
  readonly toast: ToastItem;
  readonly onDismiss: (id: number) => void;
}) {
  const { t } = useI18n();

  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(toast.id), LIFETIME_MS);
    return () => window.clearTimeout(timer);
  }, [onDismiss, toast.id]);

  const icon = TOAST_ICONS[toast.tone];

  return (
    <div
      className={`toast toast--${toast.tone}`}
      role={toast.tone === "error" ? "alert" : "status"}
    >
      <span className="toast__icon" aria-hidden="true">
        <Icon name={icon} size={17} />
      </span>
      <span className="toast__message">{toast.message}</span>
      <button
        type="button"
        className="toast__close"
        onClick={() => onDismiss(toast.id)}
        aria-label={t("core.toast.dismiss")}
      >
        <Icon name="close" size={14} />
      </button>
    </div>
  );
}

/** Accesses the toast queue from any component inside ToastProvider. */
export function useToast(): ToastValue {
  const value = use(ToastContext);
  if (!value) {
    throw new Error("useToast must be used inside <ToastProvider>.");
  }
  return value;
}
