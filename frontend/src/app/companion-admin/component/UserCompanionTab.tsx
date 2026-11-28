import { useMemo, useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useDeleteCompanionUserLoreOverrideAdmin,
  useGetCompanionUserAdmin,
  useListCompanionPresetsAdmin,
  useListCompanionUserFragmentsAdmin,
  useResetCompanionUserProgressAdmin,
  useSetCompanionUserFragmentProgressAdmin,
  useUpdateCompanionUserBondAdmin,
  useUpsertCompanionUserLoreOverrideAdmin,
} from "../../generated-apis-types";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { useAdminRefresh } from "../hook/useAdminRefresh";
import { ConstellationTimeline } from "./ConstellationTimeline";
import { FragmentGrid } from "./FragmentGrid";
import { OverridesEditor } from "./OverridesEditor";
import { PolicyEditor } from "./PolicyEditor";
import { StoryReader } from "./StoryReader";
import "../companion-admin.css";

type Locale = "en" | "zh-TW" | "zh-CN";
type Section = "sky" | "fragments" | "stories" | "overrides" | "policy";
const SECTIONS: readonly Section[] = [
  "sky",
  "fragments",
  "stories",
  "overrides",
  "policy",
];

interface UserCompanionTabProps {
  readonly userId: number;
}

function portraitFor(ref: string): string | null {
  return ref.startsWith("preset:")
    ? `/companions/${ref.slice(7)}/portrait.avif`
    : null;
}

/**
 * Root's white-box view of one account's companions: who is active and why,
 * the memory sky, every memory's state, life stories, and root's overrides.
 * The account itself never sees any of this.
 */
export function UserCompanionTab({ userId }: UserCompanionTabProps) {
  const { t, formatNumber, locale: uiLocale } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const user = useGetCompanionUserAdmin(userId, { query: { retry: false } });
  const presets = useListCompanionPresetsAdmin({
    query: { retry: false, staleTime: 60_000 },
  });
  const [chosenRef, setChosenRef] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("sky");
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [runs, setRuns] = useState("");
  const storyLocale: Locale =
    uiLocale === "zh-TW" || uiLocale === "zh-CN" ? uiLocale : "en";

  const names = useMemo(() => {
    const map = new Map<string, string>();
    for (const preset of presets.data ?? []) {
      map.set(
        `preset:${preset.id}`,
        preset.names[storyLocale] ?? preset.names.en ?? preset.id,
      );
    }
    for (const bond of user.data?.bonds ?? []) {
      if (!map.has(bond.companion_ref)) map.set(bond.companion_ref, bond.name);
    }
    return map;
  }, [presets.data, user.data, storyLocale]);

  const ref = chosenRef ?? user.data?.policy.active_ref ?? null;
  const fragments = useListCompanionUserFragmentsAdmin(
    userId,
    ref ?? "preset:vellum",
    { locale: storyLocale },
    {
      query: { retry: false, enabled: ref !== null },
    },
  );
  const progress = useSetCompanionUserFragmentProgressAdmin();
  const upsert = useUpsertCompanionUserLoreOverrideAdmin();
  const unhide = useDeleteCompanionUserLoreOverrideAdmin();
  const bondUpdate = useUpdateCompanionUserBondAdmin();
  const reset = useResetCompanionUserProgressAdmin();
  const busy =
    progress.isPending ||
    upsert.isPending ||
    unhide.isPending ||
    bondUpdate.isPending ||
    reset.isPending;

  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
      refresh();
      toast.success(t("companionAdmin.world.saved"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };

  if (user.isPending) {
    return <Loader label={t("companionAdmin.companion.loading")} />;
  }
  if (user.isError || !user.data || ref === null) {
    return (
      <p className="ca-empty" role="alert">
        {t("companionAdmin.companion.error")}
      </p>
    );
  }

  const data = user.data;
  const bond =
    data.bonds.find((item) => item.companion_ref === ref) ?? data.bonds[0];

  return (
    <div className="ca-user">
      <p className="ca-whitebox">
        <Icon name="key" size={14} />
        {t("companionAdmin.companion.whiteBox")}
      </p>

      <div
        className="ca-picker"
        role="tablist"
        aria-label={t("companionAdmin.companion.pickLabel")}
      >
        {data.bonds.map((item) => {
          const selected = item.companion_ref === ref;
          const portrait = portraitFor(item.companion_ref);
          return (
            <button
              key={item.companion_ref}
              type="button"
              role="tab"
              aria-selected={selected}
              className={`ca-picker__item${selected ? " is-selected" : ""}`}
              onClick={() => {
                setChosenRef(item.companion_ref);
                setFocusKey(null);
              }}
            >
              {portrait ? (
                <img
                  src={portrait}
                  alt=""
                  width={36}
                  height={36}
                  loading="lazy"
                  decoding="async"
                />
              ) : (
                <span className="ca-picker__glyph" aria-hidden="true">
                  <Icon name="companion" size={16} />
                </span>
              )}
              <span className="ca-picker__name">
                {names.get(item.companion_ref) ?? item.name}
              </span>
              {item.companion_ref === data.policy.active_ref ? (
                <Badge tone="moss" dot>
                  {t("companionAdmin.companion.active")} ·{" "}
                  {t(
                    `companionAdmin.companion.activeBy.${data.policy.active_source}`,
                  )}
                </Badge>
              ) : null}
            </button>
          );
        })}
      </div>

      <dl className="ca-stats">
        <div>
          <dt>{t("companionAdmin.companion.stats.runs")}</dt>
          <dd>{formatNumber(bond.completed_runs)}</dd>
        </div>
        <div>
          <dt>{t("companionAdmin.companion.stats.conversations")}</dt>
          <dd>{formatNumber(bond.conversations)}</dd>
        </div>
        <div>
          <dt>{t("companionAdmin.companion.stats.told")}</dt>
          <dd>
            {formatNumber(bond.told_count)} /{" "}
            {formatNumber(bond.fragment_count)}
          </dd>
        </div>
        <div>
          <dt>{t("companionAdmin.companion.stats.stories")}</dt>
          <dd>{formatNumber(bond.generated_count)}</dd>
        </div>
        <div>
          <dt>{t("companionAdmin.companion.stats.nextMoment")}</dt>
          <dd>
            {bond.next_story_moment_in_runs == null
              ? t("companionAdmin.companion.stats.nextMomentOff")
              : t("companionAdmin.companion.stats.nextMomentValue", {
                  count: formatNumber(bond.next_story_moment_in_runs),
                })}
          </dd>
        </div>
        <div>
          <dt>{t("companionAdmin.companion.stats.nextStory")}</dt>
          <dd>
            {bond.next_life_story_in_conversations == null
              ? t("companionAdmin.companion.stats.nextMomentOff")
              : t("companionAdmin.companion.stats.nextStoryValue", {
                  count: formatNumber(bond.next_life_story_in_conversations),
                })}
          </dd>
        </div>
      </dl>

      <div
        className="ca-sections"
        role="tablist"
        aria-label={t("companionAdmin.detail.tabsLabel")}
      >
        {SECTIONS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={section === item}
            className={`ca-sections__tab${section === item ? " is-active" : ""}`}
            onClick={() => setSection(item)}
          >
            {t(`companionAdmin.companion.sections.${item}`)}
          </button>
        ))}
      </div>

      <div className="ca-section-body" role="tabpanel">
        {(section === "sky" || section === "fragments") && !fragments.data ? (
          <Loader label={t("companionAdmin.world.loading")} />
        ) : null}
        {section === "sky" && fragments.data ? (
          <>
            <ConstellationTimeline
              bond={bond}
              fragments={fragments.data.fragments}
              portrait={portraitFor(ref)}
              onSelect={(key) => {
                setFocusKey(key);
                setSection("fragments");
              }}
            />
            <div className="ca-row ca-adjust">
              <label className="ca-field">
                <span>{t("companionAdmin.companion.adjustRunsLabel")}</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={runs}
                  placeholder={String(bond.completed_runs)}
                  onChange={(event) => setRuns(event.target.value)}
                />
              </label>
              <Button
                type="button"
                size="sm"
                disabled={busy || runs === ""}
                onClick={() =>
                  void run(() =>
                    bondUpdate.mutateAsync({
                      userId,
                      companionRef: ref,
                      data: { completed_runs: Number.parseInt(runs, 10) },
                    }),
                  ).then(() => setRuns(""))
                }
              >
                {t("companionAdmin.companion.adjustSave")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(t("companionAdmin.companion.resetConfirm"))
                  ) {
                    void run(() =>
                      reset.mutateAsync({
                        userId,
                        companionRef: ref,
                        data: { scope: "told" },
                      }),
                    );
                  }
                }}
              >
                {t("companionAdmin.companion.resetTold")}
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(t("companionAdmin.companion.resetConfirm"))
                  ) {
                    void run(() =>
                      reset.mutateAsync({
                        userId,
                        companionRef: ref,
                        data: { scope: "all" },
                      }),
                    );
                  }
                }}
              >
                {t("companionAdmin.companion.resetAll")}
              </Button>
            </div>
          </>
        ) : null}

        {section === "fragments" && fragments.data ? (
          <FragmentGrid
            fragments={fragments.data.fragments}
            focusKey={focusKey}
            busy={busy}
            onToggleTold={(key, told) =>
              void run(() =>
                progress.mutateAsync({
                  userId,
                  companionRef: ref,
                  data: { fragment_key: key, told },
                }),
              )
            }
            onToggleHidden={(key, hidden) =>
              void run(() =>
                hidden
                  ? upsert.mutateAsync({
                      userId,
                      companionRef: ref,
                      data: { fragment_key: key, action: "hide" },
                      params: { locale: storyLocale },
                    })
                  : unhide.mutateAsync({
                      userId,
                      companionRef: ref,
                      fragmentKey: key,
                      params: { locale: storyLocale },
                    }),
              )
            }
          />
        ) : null}

        {section === "stories" ? (
          <StoryReader
            userId={userId}
            companionRef={ref}
            locale={storyLocale}
            names={names}
          />
        ) : null}

        {section === "overrides" ? (
          <OverridesEditor userId={userId} companionRef={ref} />
        ) : null}

        {section === "policy" ? (
          <PolicyEditor
            key={data.policy.updated_at ?? "none"}
            userId={userId}
            policy={data.policy}
            names={names}
          />
        ) : null}
      </div>
    </div>
  );
}
