import { useMemo, useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import type { CompanionUserFragmentSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import {
  EMPTY_FILTER,
  WEIGHT_ORDER,
  filterFragments,
  isTold,
  weightOf,
  type FragmentFilter,
  type FragmentLike,
} from "../constellation";

interface FragmentGridProps {
  readonly fragments: readonly CompanionUserFragmentSchema[];
  readonly focusKey: string | null;
  readonly busy: boolean;
  readonly onToggleTold: (key: string, told: boolean) => void;
  readonly onToggleHidden: (key: string, hidden: boolean) => void;
}

const TOLD = ["all", "told", "untold"] as const;
const ORIGINS = ["all", "preset", "admin", "user", "generated"] as const;
const WEIGHT_TONE = {
  everyday: "neutral",
  past: "ochre",
  heart: "vermilion",
} as const;

type Row = CompanionUserFragmentSchema & FragmentLike;

/** Every memory for the account (nothing is locked), filterable by weight and told state. */
export function FragmentGrid({
  fragments,
  focusKey,
  busy,
  onToggleTold,
  onToggleHidden,
}: FragmentGridProps) {
  const { t, formatDate, formatNumber } = useI18n();
  const [filter, setFilter] = useState<FragmentFilter>(EMPTY_FILTER);
  const shown = useMemo(
    () => filterFragments(fragments as readonly Row[], filter),
    [fragments, filter],
  );
  const ordered = focusKey
    ? [...shown].sort(
        (a, b) => Number(b.key === focusKey) - Number(a.key === focusKey),
      )
    : shown;

  const toldLine = (fragment: Row): string => {
    const parts = [
      t("companionAdmin.fragments.toldTimes", {
        count: formatNumber(fragment.told_count),
      }),
    ];
    if (fragment.source)
      parts.push(t(`companionAdmin.fragments.sourceLabel.${fragment.source}`));
    if (fragment.last_told_at) {
      parts.push(
        t("companionAdmin.fragments.lastTold", {
          date: formatDate(fragment.last_told_at),
        }),
      );
    }
    return parts.join(" · ");
  };

  return (
    <div className="ca-fragments">
      <div className="ca-filters">
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.fragments.searchLabel")}</span>
          <input
            type="search"
            className="input"
            value={filter.query}
            placeholder={t("companionAdmin.fragments.searchPlaceholder")}
            onChange={(event) =>
              setFilter({ ...filter, query: event.target.value })
            }
          />
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.weight")}</span>
          <select
            className="input"
            value={filter.weight}
            onChange={(event) =>
              setFilter({
                ...filter,
                weight: event.target.value as FragmentFilter["weight"],
              })
            }
          >
            <option value="all">{t("companionAdmin.fragments.any")}</option>
            {WEIGHT_ORDER.map((weight) => (
              <option key={weight} value={weight}>
                {t(`companionAdmin.fragments.weights.${weight}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.state")}</span>
          <select
            className="input"
            value={filter.told}
            onChange={(event) =>
              setFilter({
                ...filter,
                told: event.target.value as FragmentFilter["told"],
              })
            }
          >
            {TOLD.map((value) => (
              <option key={value} value={value}>
                {value === "all"
                  ? t("companionAdmin.fragments.any")
                  : t(`companionAdmin.fragments.states.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.origin")}</span>
          <select
            className="input"
            value={filter.origin}
            onChange={(event) =>
              setFilter({
                ...filter,
                origin: event.target.value as FragmentFilter["origin"],
              })
            }
          >
            {ORIGINS.map((origin) => (
              <option key={origin} value={origin}>
                {origin === "all"
                  ? t("companionAdmin.fragments.any")
                  : t(`companionAdmin.fragments.origins.${origin}`)}
              </option>
            ))}
          </select>
        </label>
        <p className="ca-filters__count">
          {t("companionAdmin.fragments.count", {
            shown: formatNumber(shown.length),
            total: formatNumber(fragments.length),
          })}
        </p>
      </div>

      {ordered.length === 0 ? (
        <p className="ca-empty">{t("companionAdmin.fragments.empty")}</p>
      ) : (
        <ul className="ca-fragment-grid">
          {ordered.map((fragment) => {
            const told = isTold(fragment);
            const weight = weightOf(fragment);
            const classes = [
              "ca-fragment",
              `ca-fragment--${told ? "told" : "untold"}`,
              `ca-fragment--${weight}`,
              fragment.hidden_by_admin ? "is-hidden" : "",
              fragment.key === focusKey ? "is-focused" : "",
            ];
            return (
              <li
                key={fragment.key}
                className={classes.filter(Boolean).join(" ")}
              >
                <header className="ca-fragment__head">
                  <code>{fragment.key}</code>
                  <Badge tone={WEIGHT_TONE[weight]} dot>
                    {t(`companionAdmin.fragments.weights.${weight}`)}
                  </Badge>
                </header>
                <p className="ca-fragment__meta">
                  {[
                    told
                      ? t("companionAdmin.fragments.states.told")
                      : t("companionAdmin.fragments.states.untold"),
                    t(`companionAdmin.fragments.origins.${fragment.origin}`),
                    fragment.hidden_by_admin
                      ? t("companionAdmin.fragments.hiddenBadge")
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
                <p className="ca-fragment__text">{fragment.text}</p>
                {told ? (
                  <p className="ca-fragment__told">{toldLine(fragment)}</p>
                ) : null}
                <footer className="ca-fragment__actions">
                  {fragment.hidden_by_admin ? null : (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => onToggleTold(fragment.key, !told)}
                    >
                      {told
                        ? t("companionAdmin.fragments.markUntold")
                        : t("companionAdmin.fragments.markTold")}
                    </Button>
                  )}
                  {fragment.origin === "preset" || fragment.hidden_by_admin ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() =>
                        onToggleHidden(fragment.key, !fragment.hidden_by_admin)
                      }
                    >
                      {fragment.hidden_by_admin
                        ? t("companionAdmin.fragments.unhide")
                        : t("companionAdmin.fragments.hide")}
                    </Button>
                  ) : null}
                </footer>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
