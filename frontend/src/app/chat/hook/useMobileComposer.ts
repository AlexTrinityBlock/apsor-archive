import { useEffect, useState } from "react";

/** Touch-first phones and narrow windows where the Send button is the submit affordance. */
const MOBILE_COMPOSER_QUERY = "(pointer: coarse), (max-width: 620px)";

/**
 * True when the composer should keep Enter as a newline instead of submitting.
 * The query covers touch devices and very narrow desktop windows; a desktop
 * keyboard keeps Enter-to-send.
 */
export function useMobileComposer(): boolean {
  const [mobile, setMobile] = useState(() =>
    typeof window === "undefined"
      ? false
      : window.matchMedia(MOBILE_COMPOSER_QUERY).matches,
  );

  useEffect(() => {
    const media = window.matchMedia(MOBILE_COMPOSER_QUERY);
    const update = () => setMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return mobile;
}
