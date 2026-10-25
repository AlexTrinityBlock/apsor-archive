import { useEffect, useState } from "react";

import { useI18n } from "../i18n";
import { Icon } from "./Icon";
import { useToast } from "./Toast";

interface CopyButtonProps {
  readonly value: string;
  readonly label?: string;
  readonly title?: string;
  readonly className?: string;
  readonly disabled?: boolean;
  readonly iconOnly?: boolean;
}

async function writeClipboard(value: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.top = "-1000px";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) {
    throw new Error("The browser rejected the copy command.");
  }
}

/**
 * One-click clipboard button with a transient Copied state.
 *
 * The label stays available to screen readers even in icon-only mode, and the
 * fallback keeps copying usable in older or non-secure browser contexts.
 */
export function CopyButton({
  value,
  label,
  title,
  className,
  disabled = false,
  iconOnly = false,
}: CopyButtonProps) {
  const { t } = useI18n();
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const resolvedLabel = label ?? t("core.copy.copy");

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(false), 1_600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    if (disabled || value.length === 0) {
      return;
    }
    try {
      await writeClipboard(value);
      setCopied(true);
      toast.success(t("core.copy.copiedToast"));
    } catch {
      toast.error(t("core.copy.failed"));
    }
  };

  return (
    <button
      type="button"
      className={[
        "copy-button",
        iconOnly ? "is-icon-only" : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => void copy()}
      disabled={disabled || value.length === 0}
      title={title ?? resolvedLabel}
      aria-label={resolvedLabel}
    >
      <Icon name={copied ? "check" : "copy"} size={13} />
      {iconOnly ? null : (
        <span aria-live="polite">
          {copied ? t("core.copy.copied") : resolvedLabel}
        </span>
      )}
    </button>
  );
}
