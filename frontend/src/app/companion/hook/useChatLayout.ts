import { useEffect, useState } from "react";

import type { LayoutContext, Rect } from "../layout";

export interface ChatLayoutSnapshot {
  readonly context: LayoutContext;
  readonly dialogOpen: boolean;
}

/** Selectors for the chat surfaces the companion must not cover. */
export const CHAT_LAYOUT_SELECTORS = {
  panel: ".chat-stream-panel",
  composer: ".chat-composer-dock",
  column: ".chat-stream__inner",
  scroller: ".chat-stream__scroll",
  // The companion's free space is the chat panel, not the whole main area:
  // the conversation rail and the inspector are content too, so a gutter
  // measured against `.app-main` would count the inspector as empty room.
  content: ".chat-stream-panel",
} as const;

const POLL_MS = 450;
/** Text sits inside the column's padding; a sliver of padding is fair game. */
const COLUMN_INSET = 14;

function rectOf(selector: string): Rect | null {
  const element = document.querySelector(selector);
  if (!(element instanceof HTMLElement) || element.offsetParent === null) {
    return null;
  }
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return null;
  }
  return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
}

function visibleColumn(): Rect | null {
  const column = rectOf(CHAT_LAYOUT_SELECTORS.column);
  const scroller = rectOf(CHAT_LAYOUT_SELECTORS.scroller);
  if (column === null || scroller === null) {
    return null;
  }
  const top = Math.max(column.top, scroller.top);
  const bottom = Math.min(column.top + column.height, scroller.top + scroller.height);
  if (bottom <= top) {
    return null;
  }
  return {
    left: column.left + COLUMN_INSET,
    top,
    width: Math.max(0, column.width - COLUMN_INSET * 2),
    height: bottom - top,
  };
}

function isDialogOpen(): boolean {
  const dialogs = document.querySelectorAll('[aria-modal="true"], dialog[open]');
  for (const dialog of dialogs) {
    if (dialog instanceof HTMLElement && !dialog.closest("[data-companion-root]")) {
      if (dialog.getClientRects().length > 0) {
        return true;
      }
    }
  }
  return false;
}

function measure(): ChatLayoutSnapshot {
  // Positions are stored against the stable layout viewport; the visual
  // viewport (shrunk by an on-screen keyboard, offset by pinch-zoom) is the
  // band the figure must stay inside.
  const visual = window.visualViewport;
  return {
    context: {
      viewport: { width: window.innerWidth, height: window.innerHeight },
      visible:
        visual === null || visual === undefined
          ? null
          : {
              top: visual.offsetTop,
              bottom: visual.offsetTop + visual.height,
              left: visual.offsetLeft,
              right: visual.offsetLeft + visual.width,
            },
      panel: rectOf(CHAT_LAYOUT_SELECTORS.panel),
      composer: rectOf(CHAT_LAYOUT_SELECTORS.composer),
      column: visibleColumn(),
      content: rectOf(CHAT_LAYOUT_SELECTORS.content),
    },
    dialogOpen: isDialogOpen(),
  };
}

function sameRect(a: Rect | null, b: Rect | null): boolean {
  if (a === null || b === null) {
    return a === b;
  }
  return (
    Math.abs(a.left - b.left) < 1 &&
    Math.abs(a.top - b.top) < 1 &&
    Math.abs(a.width - b.width) < 1 &&
    Math.abs(a.height - b.height) < 1
  );
}

function sameBand(a: LayoutContext["visible"], b: LayoutContext["visible"]): boolean {
  if (a === null || a === undefined || b === null || b === undefined) {
    return (a ?? null) === (b ?? null);
  }
  return (
    Math.abs(a.top - b.top) < 1 &&
    Math.abs(a.bottom - b.bottom) < 1 &&
    Math.abs((a.left ?? 0) - (b.left ?? 0)) < 1 &&
    Math.abs((a.right ?? 0) - (b.right ?? 0)) < 1
  );
}

function sameSnapshot(a: ChatLayoutSnapshot, b: ChatLayoutSnapshot): boolean {
  return (
    sameBand(a.context.visible, b.context.visible) &&
    a.dialogOpen === b.dialogOpen &&
    a.context.viewport.width === b.context.viewport.width &&
    a.context.viewport.height === b.context.viewport.height &&
    sameRect(a.context.panel, b.context.panel) &&
    sameRect(a.context.composer, b.context.composer) &&
    sameRect(a.context.column, b.context.column) &&
    sameRect(a.context.content ?? null, b.context.content ?? null)
  );
}

const EMPTY: ChatLayoutSnapshot = {
  context: { viewport: { width: 1280, height: 800 }, panel: null, composer: null, column: null },
  dialogOpen: false,
};

/**
 * Track the chat surfaces with a cheap poll plus resize events. Polling keeps
 * the hook independent of how the chat page renders dialogs and drawers, and
 * stops while the tab is hidden.
 */
export function useChatLayout(enabled: boolean): ChatLayoutSnapshot {
  const [snapshot, setSnapshot] = useState<ChatLayoutSnapshot>(EMPTY);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next = measure();
        setSnapshot((current) => (sameSnapshot(current, next) ? current : next));
      });
    };
    update();
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        update();
      }
    }, POLL_MS);
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      cancelAnimationFrame(frame);
      window.clearInterval(interval);
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [enabled]);

  return snapshot;
}
