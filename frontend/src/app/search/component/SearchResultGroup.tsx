import { useId, type ReactNode } from "react";

interface SearchResultGroupProps {
  readonly index: string;
  readonly eyebrow: string;
  readonly title: string;
  readonly accent: "moss" | "vermilion" | "ochre";
  readonly count: number;
  readonly emptyLabel: string;
  readonly children: ReactNode;
}

/** One source-kind shelf within the fused result set. */
export function SearchResultGroup({
  index,
  eyebrow,
  title,
  accent,
  count,
  emptyLabel,
  children,
}: SearchResultGroupProps) {
  const headingId = useId();
  const countLabel = String(count).padStart(2, "0");

  return (
    <section
      className={`search-group search-group--${accent}`}
      aria-labelledby={headingId}
    >
      <header className="search-group__head">
        <div>
          <p className="eyebrow">
            {index} · {eyebrow}
          </p>
          <h2 id={headingId}>{title}</h2>
        </div>
        <span className="search-group__count">
          {countLabel} {count === 1 ? "result" : "results"}
        </span>
      </header>

      {count > 0 ? <div className="search-group__list">{children}</div> : <p className="search-group__empty">{emptyLabel}</p>}
    </section>
  );
}
