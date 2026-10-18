interface LoaderProps {
  readonly size?: number;
  readonly label?: string;
  readonly className?: string;
}

/** A small tree-ring spinner for pending queries and route transitions. */
export function Loader({ size = 36, label = "Loading the archive", className }: LoaderProps) {
  return (
    <span
      className={["loader", className].filter(Boolean).join(" ")}
      role="status"
      aria-live="polite"
    >
      <svg
        viewBox="0 0 48 48"
        width={size}
        height={size}
        fill="none"
        aria-hidden="true"
        focusable="false"
        className="loader__rings"
      >
        <circle cx="24" cy="24" r="19" stroke="currentColor" strokeOpacity=".18" />
        <circle cx="24" cy="24" r="12.5" stroke="currentColor" strokeOpacity=".32" />
        <circle
          cx="24"
          cy="24"
          r="19"
          stroke="currentColor"
          strokeLinecap="round"
          strokeDasharray="24 96"
          className="loader__arc"
        />
        <circle cx="24" cy="24" r="2.2" fill="currentColor" />
      </svg>
      <span className="visually-hidden">{label}</span>
    </span>
  );
}
