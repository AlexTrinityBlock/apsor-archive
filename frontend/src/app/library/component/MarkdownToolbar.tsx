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
  /** 沒有對應線稿圖示時顯示的短標記（B、I、H1…）。 */
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
 * Markdown 格式工具列。
 *
 * 按下按鈕時先阻止 mousedown 的預設行為，避免 textarea 失焦後選取範圍
 * 消失；實際套用時再用記住的選取範圍取代內容，最後把焦點與選取範圍還給
 * textarea。
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

    // 等 React 提交新的 value 後再設定選取範圍，否則瀏覽器會把游標推到結尾。
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
