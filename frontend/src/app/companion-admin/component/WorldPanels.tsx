import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useApplyCompanionSeedAdmin,
  useGetCompanionConfigAdmin,
  useGetCompanionPresetTextAdmin,
  useGetCompanionSeedStatusAdmin,
  useListCompanionCanonAdmin,
  useListCompanionPresetsAdmin,
  useResetCompanionConfigAdmin,
  useResetCompanionPresetTextAdmin,
  useUpdateCompanionConfigAdmin,
  useUpdateCompanionPresetAdmin,
  useUpdateCompanionPresetTextAdmin,
  useUpsertCompanionCanonEntityAdmin,
} from "../../generated-apis-types";
import type {
  CompanionPresetAdminSchema,
  CompanionPresetTextAdminSchema,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { useAdminRefresh } from "../hook/useAdminRefresh";
import { ConfigKnobs } from "./ConfigKnobs";

type Locale = "en" | "zh-TW" | "zh-CN";
const LOCALES: readonly Locale[] = ["en", "zh-TW", "zh-CN"];

function useRunner() {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  return async (action: () => Promise<unknown>) => {
    try {
      await action();
      refresh();
      toast.success(t("companionAdmin.world.saved"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };
}

/** The six librarians: availability, order, the global default, and personas. */
export function PresetsPanel() {
  const { t, formatNumber } = useI18n();
  const presets = useListCompanionPresetsAdmin({ query: { retry: false } });
  const update = useUpdateCompanionPresetAdmin();
  const run = useRunner();
  const [editing, setEditing] = useState<string | null>(null);
  if (presets.isPending)
    return <Loader label={t("companionAdmin.world.loading")} />;
  return (
    <ul className="ca-preset-grid">
      {(presets.data ?? []).map((preset: CompanionPresetAdminSchema) => (
        <li
          key={preset.id}
          className={`ca-preset${preset.enabled ? "" : " is-disabled"}`}
        >
          <img
            className="ca-preset__portrait"
            src={`/companions/${preset.id}/portrait.avif`}
            alt=""
            width={96}
            height={96}
            loading="lazy"
            decoding="async"
          />
          <div className="ca-preset__body">
            <h4>{preset.names.en ?? preset.id}</h4>
            <p className="ca-hint">
              {[
                ...new Set(
                  LOCALES.map((locale) => preset.names[locale]).filter(Boolean),
                ),
              ].join(" · ")}
            </p>
            <p className="ca-hint">
              {t("companionAdmin.presets.fragments", {
                count: formatNumber(preset.fragment_count),
              })}
            </p>
            <div className="ca-row">
              {preset.is_global_default ? (
                <Badge tone="moss" dot>
                  {t("companionAdmin.presets.default")}
                </Badge>
              ) : null}
              {!preset.seeded ? (
                <Badge tone="neutral">
                  {t("companionAdmin.world.seededOnly")}
                </Badge>
              ) : null}
              {preset.admin_modified ? (
                <Badge tone="ochre">{t("companionAdmin.world.modified")}</Badge>
              ) : null}
              {preset.upstream_changed ? (
                <Badge tone="vermilion">
                  {t("companionAdmin.world.upstream")}
                </Badge>
              ) : null}
            </div>
            <div className="ca-actions">
              <label className="ca-check">
                <input
                  type="checkbox"
                  checked={preset.enabled}
                  disabled={update.isPending}
                  onChange={(event) =>
                    void run(() =>
                      update.mutateAsync({
                        presetId: preset.id,
                        data: { enabled: event.target.checked },
                      }),
                    )
                  }
                />
                {t("companionAdmin.presets.enabled")}
              </label>
              {!preset.is_global_default ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={update.isPending || !preset.enabled}
                  onClick={() =>
                    void run(() =>
                      update.mutateAsync({
                        presetId: preset.id,
                        data: { is_global_default: true },
                      }),
                    )
                  }
                >
                  {t("companionAdmin.presets.makeDefault")}
                </Button>
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() =>
                  setEditing(editing === preset.id ? null : preset.id)
                }
              >
                {t("companionAdmin.presets.editPersona")}
              </Button>
            </div>
          </div>
          {editing === preset.id ? (
            <PresetTextEditor presetId={preset.id} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function PresetTextEditor({ presetId }: { readonly presetId: string }) {
  const { t } = useI18n();
  const [locale, setLocale] = useState<Locale>("en");
  const text = useGetCompanionPresetTextAdmin(
    presetId,
    { locale },
    { query: { retry: false } },
  );
  return (
    <div className="ca-preset__editor">
      <div
        className="ca-seg"
        role="group"
        aria-label={t("companionAdmin.overrides.locale")}
      >
        {LOCALES.map((item) => (
          <button
            key={item}
            type="button"
            className={locale === item ? "is-on" : ""}
            aria-pressed={locale === item}
            onClick={() => setLocale(item)}
          >
            {t(`companionAdmin.locales.${item}`)}
          </button>
        ))}
      </div>
      {text.data ? (
        <PresetTextForm
          key={`${locale}-${text.data.updated_at ?? "seed"}`}
          data={text.data}
        />
      ) : (
        <Loader label={t("companionAdmin.world.loading")} />
      )}
    </div>
  );
}

function PresetTextForm({
  data,
}: {
  readonly data: CompanionPresetTextAdminSchema;
}) {
  const { t } = useI18n();
  const run = useRunner();
  const update = useUpdateCompanionPresetTextAdmin();
  const reset = useResetCompanionPresetTextAdmin();
  const [name, setName] = useState(data.name);
  const [persona, setPersona] = useState(data.persona);
  return (
    <>
      <label className="ca-field">
        <span>{t("companionAdmin.presets.name")}</span>
        <input
          className="input"
          maxLength={40}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label className="ca-field">
        <span>{t("companionAdmin.presets.persona")}</span>
        <textarea
          className="input"
          rows={8}
          maxLength={4000}
          value={persona}
          onChange={(event) => setPersona(event.target.value)}
        />
      </label>
      <div className="ca-actions">
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={update.isPending || !name.trim() || !persona.trim()}
          onClick={() =>
            void run(() =>
              update.mutateAsync({
                presetId: data.preset_id,
                data: { name, persona },
                params: { locale: data.locale },
              }),
            )
          }
        >
          {t("companionAdmin.world.save")}
        </Button>
        {data.admin_modified ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={reset.isPending}
            onClick={() =>
              void run(() =>
                reset.mutateAsync({
                  presetId: data.preset_id,
                  params: { locale: data.locale },
                }),
              )
            }
          >
            {t("companionAdmin.world.reset")}
          </Button>
        ) : null}
      </div>
    </>
  );
}

/** Canon entities: names and one-line summaries per locale. */
export function CanonPanel() {
  const { t } = useI18n();
  const [locale, setLocale] = useState<Locale>("en");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const canon = useListCompanionCanonAdmin(
    { locale },
    { query: { retry: false } },
  );
  const upsert = useUpsertCompanionCanonEntityAdmin();
  const run = useRunner();
  const needle = query.trim().toLowerCase();
  const rows = (canon.data ?? []).filter(
    (row) =>
      !needle ||
      row.entity_id.includes(needle) ||
      row.name.toLowerCase().includes(needle) ||
      row.summary.toLowerCase().includes(needle),
  );
  return (
    <div className="ca-canon">
      <div className="ca-filters">
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.canon.search")}</span>
          <input
            type="search"
            className="input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="ca-field">
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
      </div>
      {canon.isPending ? (
        <Loader label={t("companionAdmin.world.loading")} />
      ) : (
        <dl className="ca-canon-list">
          {rows.map((row) => (
            <div key={row.entity_id} className="ca-canon-item">
              <dt>
                <code>{row.entity_id}</code> {row.name}
                {row.admin_modified ? (
                  <Badge tone="ochre">
                    {t("companionAdmin.world.modified")}
                  </Badge>
                ) : null}
              </dt>
              {editing === row.entity_id ? (
                <CanonForm
                  initialName={row.name}
                  initialSummary={row.summary}
                  busy={upsert.isPending}
                  onSave={(name, summary) =>
                    void run(() =>
                      upsert.mutateAsync({
                        data: {
                          entity_id: row.entity_id,
                          locale,
                          name,
                          summary,
                        },
                      }),
                    ).then(() => setEditing(null))
                  }
                />
              ) : (
                <dd>
                  {row.summary}{" "}
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => setEditing(row.entity_id)}
                  >
                    {t("companionAdmin.lore.edit")}
                  </button>
                </dd>
              )}
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function CanonForm({
  initialName,
  initialSummary,
  busy,
  onSave,
}: {
  readonly initialName: string;
  readonly initialSummary: string;
  readonly busy: boolean;
  readonly onSave: (name: string, summary: string) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(initialName);
  const [summary, setSummary] = useState(initialSummary);
  return (
    <dd className="ca-canon-form">
      <input
        className="input"
        aria-label={t("companionAdmin.canon.name")}
        maxLength={120}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <textarea
        className="input"
        aria-label={t("companionAdmin.canon.summary")}
        rows={3}
        maxLength={1000}
        value={summary}
        onChange={(event) => setSummary(event.target.value)}
      />
      <Button
        type="button"
        size="sm"
        variant="primary"
        disabled={busy || !name.trim() || !summary.trim()}
        onClick={() => onSave(name, summary)}
      >
        {t("companionAdmin.world.save")}
      </Button>
    </dd>
  );
}

/** Every global pacing knob with explanations and shipped defaults. */
export function ConfigPanel() {
  const { t } = useI18n();
  const config = useGetCompanionConfigAdmin({ query: { retry: false } });
  const update = useUpdateCompanionConfigAdmin();
  const reset = useResetCompanionConfigAdmin();
  const run = useRunner();
  if (!config.data) return <Loader label={t("companionAdmin.world.loading")} />;
  return (
    <ConfigKnobs
      key={config.data.version}
      knobs={config.data.knobs}
      busy={update.isPending || reset.isPending}
      saveLabel={t("companionAdmin.world.save")}
      resetLabel={t("companionAdmin.config.resetAll")}
      onSave={(values) =>
        void run(() =>
          update.mutateAsync({
            data: {
              values: values as Record<
                string,
                number | boolean | string | string[]
              >,
            },
          }),
        )
      }
      onReset={() => {
        if (window.confirm(t("companionAdmin.config.resetConfirm"))) {
          void run(() => reset.mutateAsync());
        }
      }}
    />
  );
}

/** Whether the shipped seed is applied, and how far the database has drifted. */
export function SeedPanel() {
  const { t, formatNumber, formatDateTime } = useI18n();
  const status = useGetCompanionSeedStatusAdmin({ query: { retry: false } });
  const apply = useApplyCompanionSeedAdmin();
  const run = useRunner();
  if (!status.data) return <Loader label={t("companionAdmin.world.loading")} />;
  const data = status.data;
  return (
    <div className="ca-seed">
      <p>
        <Badge tone={data.applied ? "moss" : "ochre"} dot>
          {data.applied
            ? t("companionAdmin.seed.applied")
            : t("companionAdmin.seed.notApplied")}
        </Badge>{" "}
        {data.applied_at ? formatDateTime(data.applied_at) : ""}
        {data.content_version != null
          ? ` · ${t("companionAdmin.seed.version", { version: formatNumber(data.content_version) })}`
          : ""}
      </p>
      <ul className="ca-seed__facts">
        <li>
          {t("companionAdmin.seed.shipped", {
            presets: formatNumber(data.shipped_presets),
            fragments: formatNumber(data.shipped_fragments),
          })}
        </li>
        <li>
          {t("companionAdmin.seed.database", {
            presets: formatNumber(data.database_presets),
            fragments: formatNumber(data.database_fragments),
          })}
        </li>
        <li>
          {t("companionAdmin.seed.modified", {
            count: formatNumber(data.admin_modified_rows),
          })}
        </li>
        <li>
          {t("companionAdmin.seed.upstream", {
            count: formatNumber(data.upstream_changed_rows),
          })}
        </li>
      </ul>
      <p className="ca-hint">{t("companionAdmin.seed.applyHint")}</p>
      <Button
        type="button"
        size="sm"
        variant="primary"
        disabled={apply.isPending}
        onClick={() =>
          void run(() => apply.mutateAsync({ data: { force_keys: [] } }))
        }
      >
        {t("companionAdmin.seed.apply")}
      </Button>
    </div>
  );
}
