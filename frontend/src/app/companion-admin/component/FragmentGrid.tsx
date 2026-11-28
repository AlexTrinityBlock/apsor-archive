import { useMemo, useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import type { CompanionUserFragmentSchema } from "../../generated-apis-types/schemas";
import { useI18n } from "../../i18n";
import {
  EMPTY_FILTER,
  filterFragments,
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

const STATE_TONE = {
  told: "moss",
  unlocked: "ochre",
  locked: "neutral",
} as const;
const STATES = ["all", "told", "unlocked", "locked"] as const;
const TIERS = ["all", "first", "familiar", "rare"] as const;
const ORIGINS = ["all", "preset", "admin", "user", "generated"] as const;

/** Every effective memory for the account, filterable, with progress actions. */
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
    () =>
      filterFragments(
        fragments as readonly (FragmentLike & CompanionUserFragmentSchema)[],
        filter,
      ),
    [fragments, filter],
  );
  const ordered = focusKey
    ? [...shown].sort(
        (a, b) => Number(b.key === focusKey) - Number(a.key === focusKey),
      )
    : shown;

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
          <span>{t("companionAdmin.fragments.state")}</span>
          <select
            className="input"
            value={filter.state}
            onChange={(event) =>
              setFilter({
                ...filter,
                state: event.target.value as FragmentFilter["state"],
              })
            }
          >
            {STATES.map((state) => (
              <option key={state} value={state}>
                {state === "all"
                  ? t("companionAdmin.fragments.any")
                  : t(`companionAdmin.fragments.states.${state}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.tier")}</span>
          <select
            className="input"
            value={filter.tier}
            onChange={(event) =>
              setFilter({
                ...filter,
                tier: event.target.value as FragmentFilter["tier"],
              })
            }
          >
            {TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier === "all"
                  ? t("companionAdmin.fragments.any")
                  : t(`companionAdmin.fragments.tiers.${tier}`)}
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
          {ordered.map((fragment) => (
            <li
              key={fragment.key}
              className={`ca-fragment ca-fragment--${fragment.state}${
                fragment.hidden_by_admin ? " is-hidden" : ""
              }${fragment.key === focusKey ? " is-focused" : ""}`}
            >
              <header className="ca-fragment__head">
                <code>{fragment.key}</code>
                <Badge tone={STATE_TONE[fragment.state]} dot>
                  {t(`companionAdmin.fragments.states.${fragment.state}`)}
                </Badge>
              </header>
              <p className="ca-fragment__meta">
                {t(`companionAdmin.fragments.tiers.${fragment.tier}`)} ·{" "}
                {t(`companionAdmin.fragments.origins.${fragment.origin}`)}
                {fragment.hidden_by_admin
                  ? ` · ${t("companionAdmin.fragments.hiddenBadge")}`
                  : ""}
              </p>
              <p className="ca-fragment__text">{fragment.text}</p>
              {fragment.told_count > 0 ? (
                <p className="ca-fragment__told">
                  {t("companionAdmin.fragments.toldTimes", {
                    count: formatNumber(fragment.told_count),
                  })}
                  {fragment.source
                    ? [
                        " ",
                        t(
                          `companionAdmin.fragments.sourceLabel.${fragment.source}`,
                        ),
                      ].join("· ")
                    : ""}
                  {fragment.last_told_at
                    ? ` · ${t("companionAdmin.fragments.lastTold", { date: formatDate(fragment.last_told_at) })}`
                    : ""}
                </p>
              ) : null}
              <footer className="ca-fragment__actions">
                {!fragment.hidden_by_admin ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      onToggleTold(fragment.key, fragment.state !== "told")
                    }
                  >
                    {fragment.state === "told"
                      ? t("companionAdmin.fragments.markUntold")
                      : t("companionAdmin.fragments.markTold")}
                  </Button>
                ) : null}
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
          ))}
        </ul>
      )}
    </div>
  );
}
