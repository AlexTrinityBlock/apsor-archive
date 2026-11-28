/**
 * Shared DOCX rendering primitives.
 *
 * The viewer and the library thumbnail renderer both load `docx-preview` into
 * a sandboxed frame, so the blank document, render options, and hardening pass
 * live here instead of being duplicated. The frame never allows scripts.
 */

/** A blank, script-free document used as the `srcDoc` of a DOCX frame. */
export const DOCX_FRAME = `<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none';">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      html, body { margin: 0; padding: 0; background: #f3edde; }
      body { min-height: 0; }
    </style>
  </head>
  <body></body>
</html>`;

/** `docx-preview` options shared by the viewer and the thumbnail renderer. */
export const DOCX_OPTIONS = {
  inWrapper: true,
  breakPages: true,
  ignoreWidth: false,
  ignoreHeight: true,
  ignoreFonts: false,
  renderHeaders: true,
  renderFooters: true,
  renderFootnotes: true,
  renderEndnotes: true,
  useBase64URL: true,
  renderChanges: false,
  renderComments: false,
  renderAltChunks: false,
  hideWrapperOnPrint: true,
} as const;

/**
 * Remove every active element and event handler `docx-preview` may have copied
 * from the package. The frame already has scripts disabled; this second pass
 * keeps imported markup inert as well.
 */
export function hardenFrame(document: Document) {
  document.querySelectorAll("script, iframe, object, embed, link, base").forEach((node) => {
    node.remove();
  });
  document.querySelectorAll("meta[http-equiv='refresh' i]").forEach((node) => node.remove());
  document.querySelectorAll<HTMLAnchorElement>("a[href]").forEach((link) => {
    if (link.protocol !== "http:" && link.protocol !== "https:") {
      link.removeAttribute("href");
      return;
    }
    link.target = "_blank";
    link.rel = "noopener noreferrer nofollow";
  });
  document.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      if (attribute.name.toLowerCase().startsWith("on")) {
        element.removeAttribute(attribute.name);
      }
    }
  });
}

/** Horizontal breathing room kept around a scaled page, in CSS pixels. */
export const DOCX_FIT_GUTTER = 16;

/**
 * Scale that fits the widest DOCX page inside a frame of `frameWidth`.
 *
 * `docx-preview` centres fixed-width pages in a flex column, so a page wider
 * than a narrow frame (phone modal, chat preview panel) overflows to the left
 * where it cannot be scrolled to. Pages are scaled down to fit instead and
 * never scaled up.
 */
export function docxFitScale(frameWidth: number, pageWidth: number): number {
  if (Number.isNaN(frameWidth) || Number.isNaN(pageWidth) || frameWidth <= 0 || pageWidth <= 0) {
    return 1;
  }
  const available = Math.max(1, frameWidth - DOCX_FIT_GUTTER * 2);
  return Math.min(1, Math.round((available / pageWidth) * 1000) / 1000);
}

/** Apply `docxFitScale` to a rendered frame document; returns the scale used. */
export function fitDocxPages(frameDocument: Document, frameWidth: number): number {
  const body = frameDocument.body;
  body.style.zoom = "1";
  let pageWidth = 0;
  frameDocument.querySelectorAll<HTMLElement>("section.docx, .docx-wrapper > section").forEach((page) => {
    pageWidth = Math.max(pageWidth, page.offsetWidth);
  });
  const scale = docxFitScale(frameWidth, pageWidth);
  body.style.zoom = scale < 1 ? String(scale) : "";
  return scale;
}
