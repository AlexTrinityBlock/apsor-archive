import { useState } from "react";

import { Button } from "../../component/Button";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useDeleteCompanionUserLoreOverrideAdmin,
  useGetCompanionUserConfigAdmin,
  useGetCompanionUserPersonaOverrideAdmin,
  useListCompanionUserLoreOverridesAdmin,
  useResetCompanionUserConfigAdmin,
  useResetCompanionUserPersonaOverrideAdmin,
  useUpdateCompanionUserConfigAdmin,
  useUpdateCompanionUserPersonaOverrideAdmin,
  useUpsertCompanionUserLoreOverrideAdmin,
} from "../../generated-apis-types";
import type { CompanionPersonaOverrideSchema } from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import {
  asWeight,
} from "../constellation";
import { useAdminRefresh } from "../hook/useAdminRefresh";
import { ConfigKnobs } from "./ConfigKnobs";

type Locale = "en" | "zh-TW" | "zh-CN";
const LOCALES: readonly Locale[] = ["en", "zh-TW", "zh-CN"];

interface OverridesEditorProps {
  readonly userId: number;
  readonly companionRef: string;
}

/** Root's per-account layer: persona, added or replaced memories, and pacing. */
export function OverridesEditor({
  userId,
  companionRef,
}: OverridesEditorProps) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const [locale, setLocale] = useState<Locale>("en");
  const persona = useGetCompanionUserPersonaOverrideAdmin(
    userId,
    companionRef,
    { locale },
    {
      query: { retry: false },
    },
  );
  const overrides = useListCompanionUserLoreOverridesAdmin(
    userId,
    companionRef,
    { locale },
    {
      query: { retry: false },
    },
  );
  const config = useGetCompanionUserConfigAdmin(userId, {
    query: { retry: false },
  });
  const upsert = useUpsertCompanionUserLoreOverrideAdmin();
  const remove = useDeleteCompanionUserLoreOverrideAdmin();
  const updateConfig = useUpdateCompanionUserConfigAdmin();
  const resetConfig = useResetCompanionUserConfigAdmin();
  const [key, setKey] = useState("");
  const [tier, setTier] = useState<"first" | "familiar" | "rare">("first");
  const [text, setText] = useState("");

  const run = async (action: () => Promise<unknown>, after?: () => void) => {
    try {
      await action();
      refresh();
      toast.success(t("companionAdmin.world.saved"));
      after?.();
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };

  return (
    <div className="ca-overrides">
      <label className="ca-field ca-field--inline">
        <span>{t("companionAdmin.overrides.locale")}</span>
        <select
          className="input"
          value={locale}
          onChange={(event) => setLocale(event.target.value as Locale)}
        >
          {LOCALES.map((item) => (
            <option key={item} value={item}>
              {t(`companionAdmin.locales.${item}`)}
            </option>
          ))}
        </select>
      </label>

      <section className="ca-subsection">
        <h4>{t("companionAdmin.overrides.personaTitle")}</h4>
        <p className="ca-hint">{t("companionAdmin.overrides.personaHint")}</p>
        {persona.data ? (
          <PersonaForm
            key={`${locale}-${persona.data.updated_at ?? "none"}`}
            userId={userId}
            companionRef={companionRef}
            locale={locale}
            data={persona.data}
          />
        ) : (
          <Loader label={t("companionAdmin.world.loading")} />
        )}
      </section>

      <section className="ca-subsection">
        <h4>{t("companionAdmin.overrides.loreList")}</h4>
        {(overrides.data ?? []).length === 0 ? (
          <p className="ca-empty">{t("companionAdmin.overrides.loreNone")}</p>
        ) : (
          <ul className="ca-override-list">
            {(overrides.data ?? []).map((row) => (
              <li key={row.fragment_key}>
                <code>{row.fragment_key}</code>
                <span className="ca-override-list__action">
                  {t(`companionAdmin.overrides.actions.${row.action}`)}
                </span>
                {row.text ? (
                  <span className="ca-override-list__text">{row.text}</span>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={remove.isPending}
                  onClick={() =>
                    void run(() =>
                      remove.mutateAsync({
                        userId,
                        companionRef,
                        fragmentKey: row.fragment_key,
                        params: { locale },
                      }),
                    )
                  }
                >
                  {t("companionAdmin.overrides.loreRemove")}
                </Button>
              </li>
            ))}
          </ul>
        )}
        <h4>{t("companionAdmin.overrides.loreTitle")}</h4>
        <div className="ca-row">
          <label className="ca-field">
            <span>{t("companionAdmin.overrides.loreKey")}</span>
            <input
              className="input"
              value={key}
              pattern="[a-z0-9][a-z0-9-]*"
              placeholder="admin-note-1"
              onChange={(event) => setKey(event.target.value.toLowerCase())}
            />
          </label>
          <label className="ca-field">
            <span>{t("companionAdmin.overrides.loreTier")}</span>
            <select
              className="input"
              value={tier}
              onChange={(event) => setTier(event.target.value as typeof tier)}
            >
              {(["first", "familiar", "rare"] as const).map((item) => (
                <option key={item} value={item}>
                  {t(`companionAdmin.fragments.weights.${asWeight(item)}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="ca-field">
          <span>{t("companionAdmin.overrides.loreText")}</span>
          <textarea
            className="input"
            rows={4}
            maxLength={2000}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <div className="ca-actions">
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={
              upsert.isPending ||
              !/^[a-z0-9][a-z0-9-]*$/.test(key) ||
              !text.trim()
            }
            onClick={() =>
              void run(
                () =>
                  upsert.mutateAsync({
                    userId,
                    companionRef,
                    data: { fragment_key: key, action: "add", weight: asWeight(tier), text },
                    params: { locale },
                  }),
                () => {
                  setKey("");
                  setText("");
                },
              )
            }
          >
            {t("companionAdmin.overrides.loreAdd")}
          </Button>
        </div>
      </section>

      <section className="ca-subsection">
        <h4>{t("companionAdmin.overrides.knobsTitle")}</h4>
        <p className="ca-hint">{t("companionAdmin.overrides.knobsHint")}</p>
        {config.data ? (
          <ConfigKnobs
            key={config.data.updated_at ?? "none"}
            knobs={config.data.knobs}
            overrides={
              config.data.overrides as Record<
                string,
                number | boolean | string | null
              >
            }
            busy={updateConfig.isPending || resetConfig.isPending}
            saveLabel={t("companionAdmin.overrides.knobsSave")}
            resetLabel={t("companionAdmin.overrides.knobsReset")}
            onSave={(values) =>
              void run(() =>
                updateConfig.mutateAsync({
                  userId,
                  data: {
                    values: values as Record<
                      string,
                      number | boolean | string | null
                    >,
                  },
                }),
              )
            }
            onReset={() => void run(() => resetConfig.mutateAsync({ userId }))}
          />
        ) : (
          <Loader label={t("companionAdmin.world.loading")} />
        )}
      </section>
    </div>
  );
}

function PersonaForm({
  userId,
  companionRef,
  locale,
  data,
}: {
  readonly userId: number;
  readonly companionRef: string;
  readonly locale: Locale;
  readonly data: CompanionPersonaOverrideSchema;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const [persona, setPersona] = useState(data.persona ?? "");
  const update = useUpdateCompanionUserPersonaOverrideAdmin();
  const reset = useResetCompanionUserPersonaOverrideAdmin();
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
      refresh();
      toast.success(t("companionAdmin.world.saved"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };
  return (
    <>
      <textarea
        className="input ca-persona"
        rows={7}
        maxLength={4000}
        value={persona}
        placeholder={data.inherited_persona}
        aria-label={t("companionAdmin.overrides.personaTitle")}
        onChange={(event) => setPersona(event.target.value)}
      />
      <details className="ca-inherited">
        <summary>{t("companionAdmin.overrides.personaInherited")}</summary>
        <p>{data.inherited_persona}</p>
      </details>
      <div className="ca-actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          disabled={update.isPending || !persona.trim()}
          onClick={() =>
            void run(() =>
              update.mutateAsync({
                userId,
                companionRef,
                data: { persona },
                params: { locale },
              }),
            )
          }
        >
          {t("companionAdmin.overrides.personaSave")}
        </Button>
        {data.persona ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={reset.isPending}
            onClick={() =>
              void run(() =>
                reset.mutateAsync({ userId, companionRef, params: { locale } }),
              )
            }
          >
            {t("companionAdmin.overrides.personaReset")}
          </Button>
        ) : null}
      </div>
    </>
  );
}
