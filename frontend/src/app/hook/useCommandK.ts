import { useEffect } from "react";

/**
 * Binds Cmd+K and Ctrl+K to the command palette.
 *
 * @param onOpen - Called when the shortcut fires. Should be referentially stable.
 */
export function useCommandK(onOpen: () => void): void {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpen();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onOpen]);
}
