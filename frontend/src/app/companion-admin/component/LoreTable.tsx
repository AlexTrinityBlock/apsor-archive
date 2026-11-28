import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useCreateCompanionLoreAdmin,
  useListCompanionLoreAdmin,
  useListCompanionPresetsAdmin,
  useResetCompanionLoreAdmin,
  useRetireCompanionLoreAdmin,
  useUpdateCompanionLoreAdmin,
} from "../../generated-apis-types";
import type {
  CompanionLoreItemAdminSchema,
  ListCompanionLoreAdminParams,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { useAdminRefresh } from "../hook/useAdminRefresh";

type Locale = "en" | "zh-TW" | "zh-CN";
type Tier = "first" | "familiar" | "rare";

const splitList = (value: string): string[] =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

/** Global lore: search and filter every librarian's memories, edit, retire, restore. */
export function LoreTable() {
  const { t, formatNumber } = useI18n();
  const [locale, setLocale] = useState<Locale>("en");
  const [preset, setPreset] = useState("");
  const [tier, setTier] = useState<Tier | "">("");
  const [query, setQuery] = useState("");
  const [upstreamOnly, setUpstreamOnly] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const presets = useListCompanionPresetsAdmin({
    query: { retry: false, staleTime: 60_000 },
  });
  const params: ListCompanionLoreAdminParams = {
    locale,
    ...(preset ? { preset } : {}),
    ...(tier ? { tier } : {}),
    ...(query.trim() ? { q: query.trim() } : {}),
    ...(upstreamOnly ? { upstream_changed: true } : {}),
  };
  const lore = useListCompanionLoreAdmin(params, { query: { retry: false } });

  return (
    <div className="ca-lore">
      <div className="ca-filters">
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.fragments.searchLabel")}</span>
          <input
            type="search"
            className="input"
            value={query}
            placeholder={t("companionAdmin.fragments.searchPlaceholder")}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.lore.filterPreset")}</span>
          <select
            className="input"
            value={preset}
            onChange={(event) => setPreset(event.target.value)}
          >
            <option value="">{t("companionAdmin.lore.anyPreset")}</option>
            {(presets.data ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.names.en ?? item.id}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.tier")}</span>
          <select
            className="input"
            value={tier}
            onChange={(event) => setTier(event.target.value as Tier | "")}
          >
            <option value="">{t("companionAdmin.fragments.any")}</option>
            {(["first", "familiar", "rare"] as const).map((item) => (
              <option key={item} value={item}>
                {t(`companionAdmin.fragments.tiers.${item}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.overrides.locale")}</span>
          <select
            className="input"
            value={locale}
            onChange={(event) => setLocale(event.target.value as Locale)}
          >
            {(["en", "zh-TW", "zh-CN"] as const).map((item) => (
              <option key={item} value={item}>
                {t(`companionAdmin.locales.${item}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-check">
          <input
            type="checkbox"
            checked={upstreamOnly}
            onChange={(event) => setUpstreamOnly(event.target.checked)}
          />
          {t("companionAdmin.lore.upstreamOnly")}
        </label>
        <Button
          type="button"
          size="sm"
          variant="primary"
          onClick={() => setCreating(!creating)}
        >
          {t("companionAdmin.lore.new")}
        </Button>
      </div>
      {creating ? (
        <LoreCreateForm
          presets={(presets.data ?? []).map((item) => item.id)}
          locale={locale}
          onDone={() => setCreating(false)}
        />
      ) : null}
      {lore.isPending ? (
        <Loader label={t("companionAdmin.world.loading")} />
      ) : (
        <>
          <p className="ca-filters__count">
            {t("companionAdmin.lore.count", {
              count: formatNumber(lore.data?.length ?? 0),
            })}
          </p>
          <ul className="ca-lore-list">
            {(lore.data ?? []).map((item) => {
              const id = `${item.preset_id}/${item.fragment_key}`;
              return (
                <li
                  key={id}
                  className={`ca-lore-item${item.retired ? " is-retired" : ""}`}
                >
                  {editing === id ? (
                    <LoreEditForm
                      item={item}
                      locale={locale}
                      onDone={() => setEditing(null)}
                    />
                  ) : (
                    <LoreRow item={item} onEdit={() => setEditing(id)} />
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}

function LoreRow({
  item,
  onEdit,
}: {
  readonly item: CompanionLoreItemAdminSchema;
  readonly onEdit: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const retire = useRetireCompanionLoreAdmin();
  const reset = useResetCompanionLoreAdmin();
  const run = async (action: () => Promise<unknown>) => {
    try {
      await action();
      refresh();
      toast.success(t("companionAdmin.world.saved"));
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };
  const target = { presetId: item.preset_id, fragmentKey: item.fragment_key };
  return (
    <>
      <header className="ca-lore-item__head">
        <code>{item.fragment_key}</code>
        <span className="ca-lore-item__preset">{item.preset_id}</span>
        <Badge tone="neutral">
          {t(`companionAdmin.fragments.tiers.${item.tier}`)}
        </Badge>
        {item.id === 0 ? (
          <Badge tone="neutral">{t("companionAdmin.world.seededOnly")}</Badge>
        ) : null}
        {item.admin_modified ? (
          <Badge tone="ochre">{t("companionAdmin.world.modified")}</Badge>
        ) : null}
        {item.upstream_changed ? (
          <Badge tone="vermilion">{t("companionAdmin.world.upstream")}</Badge>
        ) : null}
        {item.retired ? (
          <Badge tone="neutral">{t("companionAdmin.lore.retired")}</Badge>
        ) : null}
      </header>
      <p className="ca-lore-item__text">{item.text}</p>
      {item.themes.length + item.refs.length > 0 ? (
        <p className="ca-lore-item__tags">
          {item.themes.map((theme) => (
            <span key={`t-${theme}`} className="ca-tag">
              {theme}
            </span>
          ))}
          {item.refs.map((ref) => (
            <span key={`r-${ref}`} className="ca-tag ca-tag--ref">
              {ref}
            </span>
          ))}
        </p>
      ) : null}
      <footer className="ca-actions">
        <Button type="button" size="sm" variant="ghost" onClick={onEdit}>
          {t("companionAdmin.lore.edit")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={retire.isPending}
          onClick={() => void run(() => retire.mutateAsync(target))}
        >
          {item.retired
            ? t("companionAdmin.lore.restore")
            : t("companionAdmin.lore.retire")}
        </Button>
        {item.admin_modified ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={reset.isPending}
            onClick={() => void run(() => reset.mutateAsync(target))}
          >
            {t("companionAdmin.world.reset")}
          </Button>
        ) : null}
      </footer>
    </>
  );
}

function LoreEditForm({
  item,
  locale,
  onDone,
}: {
  readonly item: CompanionLoreItemAdminSchema;
  readonly locale: Locale;
  readonly onDone: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const update = useUpdateCompanionLoreAdmin();
  const [text, setText] = useState(item.text);
  const [tier, setTier] = useState<Tier>(item.tier);
  const [themes, setThemes] = useState(item.themes.join(", "));
  const [refs, setRefs] = useState(item.refs.join(", "));
  const save = async () => {
    try {
      await update.mutateAsync({
        presetId: item.preset_id,
        fragmentKey: item.fragment_key,
        data: {
          text,
          tier,
          themes: splitList(themes),
          refs: splitList(refs),
          locale,
        },
      });
      refresh();
      toast.success(t("companionAdmin.world.saved"));
      onDone();
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };
  return (
    <div className="ca-lore-form">
      <code>{item.fragment_key}</code>
      <textarea
        className="input"
        rows={6}
        maxLength={2000}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <div className="ca-row">
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.tier")}</span>
          <select
            className="input"
            value={tier}
            onChange={(event) => setTier(event.target.value as Tier)}
          >
            {(["first", "familiar", "rare"] as const).map((value) => (
              <option key={value} value={value}>
                {t(`companionAdmin.fragments.tiers.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.lore.themes")}</span>
          <input
            className="input"
            value={themes}
            onChange={(event) => setThemes(event.target.value)}
          />
        </label>
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.lore.refs")}</span>
          <input
            className="input"
            value={refs}
            onChange={(event) => setRefs(event.target.value)}
          />
        </label>
      </div>
      <div className="ca-actions">
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={update.isPending || !text.trim()}
          onClick={() => void save()}
        >
          {t("companionAdmin.world.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          {t("companionAdmin.stories.close")}
        </Button>
      </div>
    </div>
  );
}

function LoreCreateForm({
  presets,
  locale,
  onDone,
}: {
  readonly presets: readonly string[];
  readonly locale: Locale;
  readonly onDone: () => void;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const create = useCreateCompanionLoreAdmin();
  const [presetId, setPresetId] = useState(presets[0] ?? "vellum");
  const [key, setKey] = useState("");
  const [tier, setTier] = useState<Tier>("first");
  const [text, setText] = useState("");
  const [themes, setThemes] = useState("");
  const [refs, setRefs] = useState("");
  const valid = /^[a-z0-9][a-z0-9-]*$/.test(key) && text.trim().length > 0;
  const save = async () => {
    try {
      await create.mutateAsync({
        data: {
          preset_id: presetId,
          fragment_key: key,
          tier,
          text,
          themes: splitList(themes),
          refs: splitList(refs),
          locale,
        },
      });
      refresh();
      toast.success(t("companionAdmin.world.saved"));
      onDone();
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };
  return (
    <div className="ca-lore-form ca-lore-form--new">
      <div className="ca-row">
        <label className="ca-field">
          <span>{t("companionAdmin.lore.filterPreset")}</span>
          <select
            className="input"
            value={presetId}
            onChange={(event) => setPresetId(event.target.value)}
          >
            {presets.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.lore.key")}</span>
          <input
            className="input"
            value={key}
            onChange={(event) => setKey(event.target.value.toLowerCase())}
          />
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.fragments.tier")}</span>
          <select
            className="input"
            value={tier}
            onChange={(event) => setTier(event.target.value as Tier)}
          >
            {(["first", "familiar", "rare"] as const).map((value) => (
              <option key={value} value={value}>
                {t(`companionAdmin.fragments.tiers.${value}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <textarea
        className="input"
        rows={5}
        maxLength={2000}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <div className="ca-row">
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.lore.themes")}</span>
          <input
            className="input"
            value={themes}
            onChange={(event) => setThemes(event.target.value)}
          />
        </label>
        <label className="ca-field ca-field--grow">
          <span>{t("companionAdmin.lore.refs")}</span>
          <input
            className="input"
            value={refs}
            onChange={(event) => setRefs(event.target.value)}
          />
        </label>
      </div>
      <div className="ca-actions">
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={!valid || create.isPending}
          onClick={() => void save()}
        >
          {t("companionAdmin.lore.create")}
        </Button>
      </div>
    </div>
  );
}
