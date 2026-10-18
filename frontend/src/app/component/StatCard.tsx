import type { StatAccent } from "../type/demo";

interface StatCardProps {
  readonly label: string;
  readonly value: string;
  readonly note: string;
  readonly accent?: StatAccent;
  readonly index?: string;
  readonly className?: string;
}

/** One segment of the archive's at-a-glance number strip. */
export function StatCard({ label, value, note, accent = "ink", index, className }: StatCardProps) {
  return (
    <article
      className={["stat-card", `stat-card--${accent}`, className].filter(Boolean).join(" ")}
    >
      <div className="stat-card__top">
        <span className="stat-card__label">{label}</span>
        {index ? <span className="stat-card__index">{index}</span> : null}
      </div>
      <span className="stat-card__value">{value}</span>
      <span className="stat-card__note">{note}</span>
    </article>
  );
}
