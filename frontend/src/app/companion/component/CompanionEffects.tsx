import type { CSSProperties, ReactNode } from "react";

import type { CompanionAction } from "../actions";

/** Particle index list; CSS staggers each particle by `--i`. */
function particles(count: number, className: string): ReactNode[] {
  return Array.from({ length: count }, (_, index) => (
    <span
      key={index}
      className={className}
      style={{ "--i": index } as CSSProperties}
    />
  ));
}

function Gear() {
  return (
    <svg className="companion-fx__gear" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8Zm8.2 4.7-1.9.4a6.6 6.6 0 0 1-.7 1.7l1.1 1.6-1.8 1.8-1.6-1.1a6.6 6.6 0 0 1-1.7.7l-.4 1.9h-2.4l-.4-1.9a6.6 6.6 0 0 1-1.7-.7l-1.6 1.1-1.8-1.8 1.1-1.6a6.6 6.6 0 0 1-.7-1.7l-1.9-.4v-2.6l1.9-.4c.2-.6.4-1.2.7-1.7L5 6.9 6.8 5l1.6 1.1c.5-.3 1.1-.6 1.7-.7l.4-1.9h2.4l.4 1.9c.6.2 1.2.4 1.7.7L16.6 5l1.8 1.8-1.1 1.6c.3.5.6 1.1.7 1.7l1.9.4Z" />
    </svg>
  );
}

function Compass() {
  return (
    <svg className="companion-fx__compass" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path className="companion-fx__needle" d="M12 4.5 14 12l-2 7.5L10 12Z" />
    </svg>
  );
}

function Lens() {
  return (
    <svg className="companion-fx__lens" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="10" cy="10" r="6" />
      <path d="m14.5 14.5 5 5" />
    </svg>
  );
}

function Quill() {
  return (
    <svg className="companion-fx__quill" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 3c-6 1-11 6-13 13l-2 5 2-1c1-3 3-5 5-6l-2-1c3 0 6-2 7-5l-2 0c2-1 4-3 5-5Z" />
    </svg>
  );
}

/**
 * Decorative, per-action flourishes. They are aria-hidden, pointer-transparent,
 * and only mounted at full motion.
 */
export function CompanionEffects({ action }: { readonly action: CompanionAction }) {
  let content: ReactNode = null;
  switch (action) {
    case "searching":
      content = (
        <>
          {particles(7, "companion-fx__mote")}
          <Lens />
        </>
      );
      break;
    case "reading":
      content = particles(3, "companion-fx__page");
      break;
    case "writing":
      content = (
        <>
          <Quill />
          {particles(5, "companion-fx__ink")}
        </>
      );
      break;
    case "calculating":
      content = (
        <>
          <Gear />
          <span className="companion-fx__gear-small">
            <Gear />
          </span>
        </>
      );
      break;
    case "browsing":
      content = <Compass />;
      break;
    case "success":
    case "greet":
      content = particles(8, "companion-fx__spark");
      break;
    case "confused":
      content = <span className="companion-fx__glyph companion-fx__glyph--question">?</span>;
      break;
    case "sleeping":
      content = particles(3, "companion-fx__zzz");
      break;
    case "thinking":
      content = (
        <span className="companion-fx__thought">
          {particles(3, "companion-fx__dot")}
        </span>
      );
      break;
    case "speaking":
      content = particles(3, "companion-fx__arc");
      break;
    case "waiting":
      content = <span className="companion-fx__pulse" />;
      break;
    case "presenting":
      content = <span className="companion-fx__spotlight" />;
      break;
    case "listening":
      content = particles(2, "companion-fx__arc companion-fx__arc--listen");
      break;
    default:
      break;
  }
  if (content === null) {
    return null;
  }
  return (
    <div className={`companion-fx companion-fx--${action}`} aria-hidden="true">
      {content}
    </div>
  );
}
