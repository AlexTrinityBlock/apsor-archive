interface TreeMarkProps {
  readonly size?: number;
  readonly className?: string;
}

/**
 * The archive's seal: concentric growth rings crossed by a single trunk.
 * Decorative by design; the adjacent wordmark carries the accessible name.
 */
export function TreeMark({ size = 40, className }: TreeMarkProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 48 48"
      width={size}
      height={size}
      fill="none"
      aria-hidden="true"
      focusable="false"
      className={className ? `tree-mark ${className}` : "tree-mark"}
    >
      <circle cx="24" cy="24" r="21" stroke="currentColor" strokeOpacity=".3" />
      <circle cx="24" cy="24" r="15.5" stroke="currentColor" strokeOpacity=".48" />
      <circle cx="24" cy="24" r="10" stroke="currentColor" strokeOpacity=".7" />
      <circle cx="24" cy="24" r="4.6" stroke="currentColor" strokeOpacity=".9" />
      <path
        d="M24 43V23m0 9c-4.3-.7-7.2-3.3-8.4-7.2M24 27.2c3.8-.6 6.7-3 8-6.7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
      <circle cx="24" cy="22.8" r="2.1" fill="currentColor" stroke="none" />
    </svg>
  );
}
