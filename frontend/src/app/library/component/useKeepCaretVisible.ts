import { useEffect, type RefObject } from "react";

const RESIZE_SETTLE_MS = 80;

/**
 * Scroll a textarea until its caret line is visible.
 *
 * A hidden mirror reproduces the textarea's typography and width, so soft-wrapped
 * lines are measured the same way the browser lays them out. This is only used
 * after a viewport change; normal typing keeps the browser's own caret scrolling.
 */
function scrollCaretIntoView(textarea: HTMLTextAreaElement): void {
  const style = window.getComputedStyle(textarea);
  const caretIndex =
    textarea.selectionDirection === "backward"
      ? textarea.selectionStart
      : textarea.selectionEnd;

  const mirror = document.createElement("div");
  mirror.setAttribute("aria-hidden", "true");
  mirror.style.position = "absolute";
  mirror.style.top = "0";
  mirror.style.left = "-9999px";
  mirror.style.width = `${textarea.clientWidth}px`;
  mirror.style.boxSizing = "border-box";
  mirror.style.border = "0";
  mirror.style.padding = style.padding;
  mirror.style.fontFamily = style.fontFamily;
  mirror.style.fontSize = style.fontSize;
  mirror.style.fontStyle = style.fontStyle;
  mirror.style.fontWeight = style.fontWeight;
  mirror.style.letterSpacing = style.letterSpacing;
  mirror.style.lineHeight = style.lineHeight;
  mirror.style.tabSize = style.tabSize;
  mirror.style.whiteSpace = style.whiteSpace;
  mirror.style.overflowWrap = style.overflowWrap;
  mirror.textContent = textarea.value.slice(0, caretIndex);
  const marker = document.createElement("span");
  marker.textContent = "\u200b";
  mirror.appendChild(marker);
  document.body.appendChild(mirror);

  const caretTop = marker.offsetTop;
  const lineHeight =
    Number.parseFloat(style.lineHeight) || marker.offsetHeight || 16;
  const viewTop = textarea.scrollTop;
  const viewBottom = viewTop + textarea.clientHeight;
  if (caretTop < viewTop) {
    textarea.scrollTop = Math.max(0, caretTop);
  } else if (caretTop + lineHeight > viewBottom) {
    textarea.scrollTop = caretTop + lineHeight - textarea.clientHeight;
  }
  mirror.remove();
}

/**
 * Keep the focused textarea's caret above the on-screen keyboard.
 *
 * Shrinking the editor for the keyboard does not make the browser re-scroll an
 * already-focused textarea, so the caret can end up below the new visible edge.
 * Resize events are debounced until the keyboard animation settles.
 */
export function useKeepCaretVisible(
  textareaRef: RefObject<HTMLTextAreaElement | null>,
): void {
  useEffect(() => {
    const viewport = window.visualViewport;
    let timer = 0;
    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const textarea = textareaRef.current;
        if (!textarea || document.activeElement !== textarea) {
          return;
        }
        scrollCaretIntoView(textarea);
      }, RESIZE_SETTLE_MS);
    };
    window.addEventListener("resize", schedule);
    viewport?.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("resize", schedule);
      viewport?.removeEventListener("resize", schedule);
      window.clearTimeout(timer);
    };
  }, [textareaRef]);
}
