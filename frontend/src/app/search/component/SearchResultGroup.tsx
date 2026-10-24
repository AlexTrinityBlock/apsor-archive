import { useId, type ReactNode } from "react";

type ResultGroupTone = "files" | "memories" | "summaries";

interface SearchResultGroupProps {
  readonly index: string;
  readonly title: string;
  readonly tone: ResultGroupTone;
  readonly count: number;
  readonly emptyLabel: string;
  readonly children: ReactNode;
}

/** One source-kind shelf within the fused result set. */
export function SearchResultGroup({
  index,
  title,
  tone,
  count,
  emptyLabel,
  children,
}: SearchResultGroupProps) {
  const headingId = useId();

  return (
    <section className={`search-group search-group--${tone}`} aria-labelledby={headingId}>
      <header className="search-group__head">
        <span className="search-group__index" aria-hidden="true">
          {index}
        </span>
        <h3 className="search-group__title" id={headingId}>
          {title}
          <span className="search-group__count">{count}</span>
        </h3>
      </header>

      {count > 0 ? (
        <div className="search-group__list">{children}</div>
      ) : (
        <p className="search-group__empty">{emptyLabel}</p>
      )}
    </section>
  );
}
