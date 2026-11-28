import { useEffect, type MutableRefObject, type RefObject } from "react";

interface DrawerAccessibilityOptions {
  readonly open: boolean;
  readonly closeButtonRef: RefObject<HTMLButtonElement | null>;
  readonly menuButtonRef: RefObject<HTMLButtonElement | null>;
  readonly returnFocusRef: MutableRefObject<boolean>;
  readonly onClose: (restoreFocus?: boolean) => void;
}

/**
 * Keeps the mobile navigation drawer's focus contract out of the page shell:
 * focus enters the drawer, Escape and explicit close return it to the menu
 * button, navigation-driven closes leave focus to the router, and a resize to
 * the desktop breakpoint closes the drawer.
 */
export function useDrawerAccessibility({
  open,
  closeButtonRef,
  menuButtonRef,
  returnFocusRef,
  onClose,
}: DrawerAccessibilityOptions): void {
  useEffect(() => {
    if (!open) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") {
        return;
      }
      returnFocusRef.current = true;
      onClose();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose, open, returnFocusRef]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [closeButtonRef, open]);

  useEffect(() => {
    if (open || !returnFocusRef.current) {
      return;
    }
    returnFocusRef.current = false;
    if (!window.matchMedia("(max-width: 980px)").matches) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      menuButtonRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [menuButtonRef, open, returnFocusRef]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 980px)");
    const closeOnDesktop = () => {
      if (!media.matches) {
        returnFocusRef.current = false;
        onClose();
      }
    };
    media.addEventListener("change", closeOnDesktop);
    return () => media.removeEventListener("change", closeOnDesktop);
  }, [onClose, returnFocusRef]);
}
