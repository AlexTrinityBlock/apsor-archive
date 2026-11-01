import { useEffect, useRef, useState } from "react";

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
 * The full-screen dialog for creating a new Markdown note.
 *
 * Escape, a background click, and the close button never unmount the component
 * directly; they all go through `MarkdownEditorHandle.requestClose()` so unsaved
 * changes get a chance to show the inline discard confirm.
 */
export function MarkdownEditorDialog({
  defaultDirectory,
  onClose,
  onSaved,
}: MarkdownEditorDialogProps) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<MarkdownEditorHandle>(null);
  const [savedFile, setSavedFile] = useState<FileSchema | null>(null);

  const handleSaved = (file: FileSchema) => {
    setSavedFile(file);
    onSaved(file);
  };

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
        // If the editor's own Escape handling has already run, do not trigger the
        // close confirmation again.
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
        aria-label={
          savedFile ? t("library.editor.editing") : t("library.editor.newNoteTitle")
        }
        tabIndex={-1}
      >
        <MarkdownEditor
          key={savedFile ? "edit" : "new"}
          ref={editorRef}
          mode={savedFile ? "edit" : "new"}
          file={savedFile ?? undefined}
          defaultDirectory={defaultDirectory}
          onCancel={onClose}
          onSaved={handleSaved}
        />
      </div>
    </div>
  );
}
