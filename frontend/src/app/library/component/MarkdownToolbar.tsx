import { useRef, type MouseEvent, type RefObject } from "react";

import { Icon, type IconName } from "../../component/Icon";
import { useI18n, type TranslationKey } from "../../i18n";
import {
  applyMarkdownAction,
  type MarkdownAction,
  type MarkdownActionLabels,
  type MarkdownEditSelection,
} from "./markdown-edit";

interface MarkdownToolbarProps {
  readonly textareaRef: RefObject<HTMLTextAreaElement | null>;
  readonly value: string;
  readonly onChange: (nextValue: string) => void;
  readonly disabled?: boolean;
}

interface ToolbarButton {
  readonly action: MarkdownAction;
  readonly labelKey: TranslationKey;
  readonly icon?: IconName;
  /** Short glyph shown when there is no matching line icon (B, I, H1, ...). */
  readonly glyph?: string;
}

function glyphClassName(action: MarkdownAction): string {
  if (action === "bold") {
    return "markdown-editor__tool-glyph is-bold";
  }
  if (action === "italic") {
    return "markdown-editor__tool-glyph is-italic";
  }
  return "markdown-editor__tool-glyph";
}

const TOOLBAR_BUTTONS: readonly ToolbarButton[] = [
  { action: "bold", labelKey: "library.editor.bold", glyph: "B" },
  { action: "italic", labelKey: "library.editor.italic", glyph: "I" },
  { action: "h1", labelKey: "library.editor.h1", glyph: "H1" },
  { action: "h2", labelKey: "library.editor.h2", glyph: "H2" },
  { action: "h3", labelKey: "library.editor.h3", glyph: "H3" },
  { action: "quote", labelKey: "library.editor.quote", icon: "quote" },
  { action: "code", labelKey: "library.editor.code", icon: "command" },
  { action: "list", labelKey: "library.editor.bulletList", icon: "menu" },
  { action: "task", labelKey: "library.editor.taskList", icon: "check" },
  { action: "link", labelKey: "library.editor.link", icon: "external" },
  { action: "table", labelKey: "library.editor.table", icon: "layers" },
];

/**
 * Markdown formatting toolbar.
 *
 * Pressing a button first prevents the default mousedown behavior so the
 * selection does not disappear when the textarea loses focus; the edit is then
 * applied against the remembered selection, and focus plus selection are handed
 * back to the textarea at the end.
 */
export function MarkdownToolbar({
  textareaRef,
  value,
  onChange,
  disabled = false,
}: MarkdownToolbarProps) {
  const { t } = useI18n();
  const selectionRef = useRef<MarkdownEditSelection | null>(null);

  const labels: MarkdownActionLabels = {
    boldPlaceholder: t("library.editor.boldPlaceholder"),
    italicPlaceholder: t("library.editor.italicPlaceholder"),
    codePlaceholder: t("library.editor.codePlaceholder"),
    linkPlaceholder: t("library.editor.linkPlaceholder"),
    tableColumnPlaceholder: t("library.editor.tableColumnPlaceholder"),
    tableCellPlaceholder: t("library.editor.tableCellPlaceholder"),
  };

  const rememberSelection = (event: MouseEvent<HTMLButtonElement>) => {
    const textarea = textareaRef.current;
    event.preventDefault();
    if (!textarea) {
      return;
    }
    selectionRef.current = {
      start: textarea.selectionStart,
      end: textarea.selectionEnd,
    };
  };

  const applyAction = (action: MarkdownAction) => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    const selection = selectionRef.current ?? {
      start: textarea.selectionStart,
      end: textarea.selectionEnd,
    };
    selectionRef.current = null;

    const edit = applyMarkdownAction(
      action,
      value,
      selection.start,
      selection.end,
      labels,
    );
    const nextValue = `${value.slice(0, edit.from)}${edit.text}${value.slice(edit.to)}`;
    onChange(nextValue);

    // Set the selection only after React commits the new value; otherwise the
    // browser pushes the caret to the end.
    window.requestAnimationFrame(() => {
      const current = textareaRef.current;
      if (!current) {
        return;
      }
      current.focus({ preventScroll: true });
      current.setSelectionRange(edit.selection.start, edit.selection.end);
    });
  };

  return (
    <div
      className="markdown-editor__toolbar"
      role="toolbar"
      aria-label={t("library.editor.toolbarLabel")}
    >
      {TOOLBAR_BUTTONS.map((button) => {
        const label = t(button.labelKey);
        return (
          <button
            key={button.action}
            type="button"
            className="markdown-editor__tool"
            aria-label={label}
            title={label}
            disabled={disabled}
            onMouseDown={rememberSelection}
            onClick={() => applyAction(button.action)}
          >
            {button.icon ? (
              <Icon name={button.icon} size={15} />
            ) : (
              <span
                className={glyphClassName(button.action)}
                aria-hidden="true"
              >
                {button.glyph}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
