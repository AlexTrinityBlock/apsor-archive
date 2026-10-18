import { useEffect, useState } from "react";

/**
 * A small reactive `matchMedia` wrapper for the library's default view.
 *
 * The board is the desktop default while the existing table remains the calm
 * mobile fallback; an explicit `view` query parameter always wins.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(query).matches,
  );

  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);

  return matches;
}
