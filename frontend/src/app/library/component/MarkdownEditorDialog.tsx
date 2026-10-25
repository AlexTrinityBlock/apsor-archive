import { useEffect, useRef } from "react";

import type { FileSchema } from "../../generated-apis-types/schemas";
import { useScrollLock } from "../../hook/useScrollLock";
import { useI18n } from "../../i18n";
import {
  MarkdownEditor,
  type MarkdownEditorHandle,
} from "./MarkdownEditor";

interface MarkdownEditorDialogProps {
  readonly defaultDirectory: string;
  readonly onClose: () => void;
  readonly onSaved: (file: FileSchema) => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * 新增 Markdown 筆記的全螢幕對話框。
 *
 * Escape、背景點擊與關閉按鈕都不直接卸載元件，而是先經過
 * `MarkdownEditorHandle.requestClose()`，讓未保存的變更有機會顯示
 * inline discard confirm。
 */
export function MarkdownEditorDialog({
  defaultDirectory,
  onClose,
  onSaved,
}: MarkdownEditorDialogProps) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<MarkdownEditorHandle>(null);

  useScrollLock(true);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = dialogRef.current;
    const initial =
      dialog?.querySelector<HTMLElement>("[data-autofocus]") ?? dialog;
    initial?.focus({ preventScroll: true });
    return () => {
      previous?.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // 編輯器自己的 Escape 處理已經執行時，不再重複觸發關閉確認。
        if (event.defaultPrevented) {
          return;
        }
        event.preventDefault();
        editorRef.current?.requestClose();
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
      className="library-dialog-layer markdown-editor-dialog-layer"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          editorRef.current?.requestClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        className="library-dialog markdown-editor-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("library.editor.newNoteTitle")}
        tabIndex={-1}
      >
        <MarkdownEditor
          ref={editorRef}
          mode="new"
          defaultDirectory={defaultDirectory}
          onCancel={onClose}
          onSaved={onSaved}
        />
      </div>
    </div>
  );
}
