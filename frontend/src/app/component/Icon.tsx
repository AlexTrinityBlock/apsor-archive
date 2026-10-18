import type { ReactNode, SVGProps } from "react";

/** Every line icon available to the archive shell and pages. */
export type IconName =
  | "overview"
  | "search"
  | "timeline"
  | "library"
  | "tree"
  | "memory"
  | "ask"
  | "method"
  | "settings"
  | "command"
  | "sun"
  | "moon"
  | "menu"
  | "close"
  | "arrow-right"
  | "arrow-up-right"
  | "arrow-down"
  | "chevron-right"
  | "chevron-down"
  | "file"
  | "folder"
  | "branch"
  | "leaf"
  | "database"
  | "layers"
  | "quote"
  | "copy"
  | "check"
  | "external"
  | "clock"
  | "info"
  | "spark"
  | "send"
  | "plus"
  | "history"
  | "filter"
  | "ring"
  | "logout";

const ICONS: Record<IconName, ReactNode> = {
  overview: (
    <>
      <path d="M3 10.7 12 3l9 7.7" />
      <path d="M5.2 9.4V21h13.6V9.4" />
      <path d="M9.4 21v-6.2h5.2V21" />
    </>
  ),
  search: (
    <>
      <circle cx="10.8" cy="10.8" r="6.3" />
      <path d="m15.4 15.4 5.1 5.1" />
    </>
  ),
  timeline: (
    <>
      <path d="M3 12h18" />
      <circle cx="7.2" cy="12" r="1.7" />
      <circle cx="12" cy="12" r="1.7" />
      <circle cx="16.8" cy="12" r="1.7" />
      <path d="M7.2 8.5V6M12 15.5V18M16.8 8.5V6" />
    </>
  ),
  library: (
    <>
      <path d="M4 4.5h3.8V20H4z" />
      <path d="M8.8 4.5H13V20H8.8z" />
      <path d="m15 5.8 3.7-.9 3 14.2-3.7.9z" />
    </>
  ),
  tree: (
    <>
      <path d="M12 21V7.5" />
      <path d="m12 14.2-6-4.4M12 10.6l6-4.4" />
      <circle cx="5.5" cy="9" r="1.4" />
      <circle cx="18.5" cy="5.4" r="1.4" />
      <path d="M8.4 21h7.2" />
    </>
  ),
  memory: (
    <>
      <path d="M6 3.8h8.7L19 8.1V20H6z" />
      <path d="M9 9h6M9 12.6h6M9 16.2h3.8" />
    </>
  ),
  ask: (
    <>
      <path d="M4 5h16v11H9.6L4 20z" />
      <path d="M9 10.5h6M12 7.5v6" />
    </>
  ),
  method: (
    <>
      <path d="M4.5 5.5c2.7-1.6 5.2-1.6 7.5 0v13c-2.3-1.6-4.8-1.6-7.5 0z" />
      <path d="M19.5 5.5c-2.7-1.6-5.2-1.6-7.5 0v13c2.3-1.6 4.8-1.6 7.5 0z" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h7M15 7h5M4 17h5M13 17h7" />
      <circle cx="13" cy="7" r="2.1" />
      <circle cx="11" cy="17" r="2.1" />
    </>
  ),
  command: (
    <path d="M9 6.5a2.5 2.5 0 1 0-2.5 2.5H9m0-2.5V9m0-2.5h6M9 9H6.5A2.5 2.5 0 1 0 9 11.5m0-2.5V6.5m6 0A2.5 2.5 0 1 1 17.5 9H15m0-2.5V9m0 0h2.5A2.5 2.5 0 1 1 15 11.5m0-2.5V6.5m-6 5A2.5 2.5 0 1 0 6.5 17.5H9m0-3.5v3.5m0-3.5h6m-6 3.5h6m0-3.5v3.5m0-3.5h2.5A2.5 2.5 0 1 0 15 17.5m0-3.5v3.5" />
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="3.8" />
      <path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6" />
    </>
  ),
  moon: <path d="M20 14.4A8.3 8.3 0 1 1 9.6 4a6.7 6.7 0 0 0 10.4 10.4Z" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  "arrow-right": (
    <>
      <path d="M4 12h15" />
      <path d="m14 6.5 5.5 5.5-5.5 5.5" />
    </>
  ),
  "arrow-up-right": (
    <>
      <path d="M6 18 18 6" />
      <path d="M8 6h10v10" />
    </>
  ),
  "arrow-down": (
    <>
      <path d="M12 4v15" />
      <path d="m5.5 12.5 6.5 6.5 6.5-6.5" />
    </>
  ),
  "chevron-right": <path d="m9 5 7 7-7 7" />,
  "chevron-down": <path d="m5 9 7 7 7-7" />,
  file: (
    <>
      <path d="M6 3.5h8l4 4V20.5H6z" />
      <path d="M14 3.5v4h4" />
    </>
  ),
  folder: <path d="M3.5 6.5h6l2 2H20.5v11H3.5z" />,
  branch: (
    <>
      <circle cx="6.5" cy="5.5" r="2.2" />
      <circle cx="6.5" cy="18.5" r="2.2" />
      <circle cx="17.5" cy="9" r="2.2" />
      <path d="M6.5 7.7v8.6M6.5 13.2c5.4 0 11-1.1 11-4.2" />
    </>
  ),
  leaf: (
    <>
      <path d="M5 19c0-8 5.2-13 14-13 0 8.8-4.8 13-11.2 13H5Z" />
      <path d="M5 19c3.5-4.2 7-6.4 11.2-8.2" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.8" rx="7.5" ry="2.8" />
      <path d="M4.5 5.8v12.4c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8V5.8" />
      <path d="M4.5 12c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8" />
    </>
  ),
  layers: (
    <>
      <path d="m12 3 9 5-9 5-9-5z" />
      <path d="m3.5 12.3 8.5 4.7 8.5-4.7M3.5 16.5l8.5 4.7 8.5-4.7" />
    </>
  ),
  quote: (
    <>
      <path d="M5 11.5h4.5V17c0 2-1.2 3.2-3.4 3.5" />
      <path d="M5 11.5C5 7.8 6.5 5.4 9.3 4M14.5 11.5H19V17c0 2-1.2 3.2-3.4 3.5" />
      <path d="M14.5 11.5c0-3.7 1.5-6.1 4.3-7.5" />
    </>
  ),
  copy: (
    <>
      <rect x="8.5" y="8.5" width="11" height="12" rx="1" />
      <path d="M15.5 5.5h-9a1 1 0 0 0-1 1v10" />
    </>
  ),
  check: <path d="m4.5 12.5 4.7 4.7L19.5 7" />,
  external: (
    <>
      <path d="M13 4.5h6.5V11" />
      <path d="m19.5 4.5-8 8" />
      <path d="M18 14v5.5H4.5V6H10" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5.3l3.5 2" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.5v.3" />
    </>
  ),
  spark: (
    <>
      <path d="m12 3 1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8z" />
      <path d="m19 17 .7 2.3L22 20l-2.3.7L19 23l-.7-2.3L16 20l2.3-.7z" />
    </>
  ),
  send: (
    <>
      <path d="m3.5 11.5 17-7-6.7 16.2-2.4-7.2z" />
      <path d="M11.4 13.5 20.5 4.5" />
    </>
  ),
  plus: <path d="M12 4v16M4 12h16" />,
  history: (
    <>
      <path d="M4.5 5.5V10H9" />
      <path d="M4.8 10A8.2 8.2 0 1 1 4 14.5" />
      <path d="M12 7.8v4.7l3.2 1.9" />
    </>
  ),
  filter: <path d="M3.5 5h17l-6.6 7.6V20l-3.8-2v-5.4z" />,
  ring: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="5.2" />
      <circle cx="12" cy="12" r="1.8" />
    </>
  ),
  logout: (
    <>
      <path d="M9.5 4H5.8A1.8 1.8 0 0 0 4 5.8v12.4A1.8 1.8 0 0 0 5.8 20h3.7" />
      <path d="M16 8l4 4-4 4" />
      <path d="M20 12H9.5" />
    </>
  ),
};

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  readonly name: IconName;
  readonly size?: number;
}

/** Renders a single stroke icon from the archive's line set. */
export function Icon({ name, size = 20, className, ...rest }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.55"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className ? `icon ${className}` : "icon"}
      {...rest}
    >
      {ICONS[name]}
    </svg>
  );
}
