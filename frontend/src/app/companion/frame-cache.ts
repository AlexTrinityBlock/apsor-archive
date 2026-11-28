/**
 * Decoded-frame cache. Poses swap only after every frame of the next clip has
 * decoded, so the figure never blinks to an empty box between poses.
 */

const decoded = new Map<string, Promise<void>>();
/** Keep decoded images referenced so the browser keeps them warm. */
const retained = new Map<string, HTMLImageElement>();
const MAX_RETAINED = 160;

export function decodeFrame(url: string): Promise<void> {
  const existing = decoded.get(url);
  if (existing !== undefined) {
    return existing;
  }
  const image = new Image();
  image.decoding = "async";
  image.src = url;
  const promise = image
    .decode()
    .catch(() => {
      if (!(image.complete && image.naturalWidth > 0)) {
        throw new Error("companion frame failed to load");
      }
    })
    .then(() => {
      retained.set(url, image);
      if (retained.size > MAX_RETAINED) {
        const oldest = retained.keys().next().value;
        if (oldest !== undefined) {
          retained.delete(oldest);
          decoded.delete(oldest);
        }
      }
    });
  promise.catch(() => decoded.delete(url));
  decoded.set(url, promise);
  return promise;
}

export function decodeFrames(urls: readonly string[]): Promise<void> {
  return Promise.all(urls.map(decodeFrame)).then(() => undefined);
}

/** Warm frames in the background when the browser is idle. */
export function preloadFrames(urls: readonly string[]): void {
  const run = () => {
    for (const url of urls) {
      void decodeFrame(url).catch(() => undefined);
    }
  };
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(run, { timeout: 2000 });
  } else {
    setTimeout(run, 300);
  }
}
