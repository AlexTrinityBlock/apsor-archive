import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useGenerateCompanionStoryAdmin,
  useListCompanionPresetsAdmin,
  useListCompanionTemplatesAdmin,
  useListCompanionUserSummariesAdmin,
  usePreviewCompanionTemplateAdmin,
  useResetCompanionTemplateAdmin,
  useUpdateCompanionTemplateAdmin,
} from "../../generated-apis-types";
import type {
  CompanionTemplateAdminSchema,
  CompanionTemplatePreviewSchema,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n, type TranslationKey } from "../../i18n";
import { templatePlaceholders } from "../constellation";
import { useAdminRefresh } from "../hook/useAdminRefresh";

/**
 * Story writing: the guidance strings and the life-story prompt. Previews use
 * an invented sample; "write a draft for an account" queues a real job whose
 * result root can read (and whose reading is recorded) like any life story.
 */
export function TemplateEditor() {
  const { t } = useI18n();
  const templates = useListCompanionTemplatesAdmin({ query: { retry: false } });
  const [selected, setSelected] = useState<string | null>(null);
  const list = templates.data ?? [];
  const current =
    selected ?? (list[0] ? `${list[0].template_key}|${list[0].locale}` : null);
  const template =
    list.find((item) => `${item.template_key}|${item.locale}` === current) ??
    null;

  return (
    <div className="ca-templates">
      <div className="ca-door ca-door--wide">
        <img
          src="/companions/world/illusory-door.avif"
          alt=""
          width={1024}
          height={683}
          loading="lazy"
          decoding="async"
          className="ca-door__art"
        />
        <p className="ca-door__copy ca-door__quote">
          {t("companionAdmin.templates.intro")}
        </p>
      </div>
      {templates.isPending ? (
        <Loader label={t("companionAdmin.world.loading")} />
      ) : (
        <>
          <label className="ca-field">
            <span>{t("companionAdmin.templates.pick")}</span>
            <select
              className="input"
              value={current ?? ""}
              onChange={(event) => setSelected(event.target.value)}
            >
              {list.map((item) => (
                <option
                  key={`${item.template_key}|${item.locale}`}
                  value={`${item.template_key}|${item.locale}`}
                >
                  {t(
                    `companionAdmin.templates.names.${item.template_key}` as TranslationKey,
                  )}{" "}
                  · {t(`companionAdmin.locales.${item.locale}`)}
                </option>
              ))}
            </select>
          </label>
          {template ? (
            <TemplateForm
              key={`${current}-${template.version}`}
              template={template}
            />
          ) : null}
        </>
      )}
      <DraftForUser />
    </div>
  );
}

function TemplateForm({
  template,
}: {
  readonly template: CompanionTemplateAdminSchema;
}) {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const [body, setBody] = useState(template.body);
  const [preview, setPreview] = useState<CompanionTemplatePreviewSchema | null>(
    null,
  );
  const update = useUpdateCompanionTemplateAdmin();
  const reset = useResetCompanionTemplateAdmin();
  const previewMutation = usePreviewCompanionTemplateAdmin();
  const used = templatePlaceholders(body);
  const missing = template.required_placeholders.filter(
    (name) => !used.includes(name),
  );

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
    <div className="ca-template">
      <div className="ca-row">
        {template.admin_modified ? (
          <Badge tone="ochre">{t("companionAdmin.world.modified")}</Badge>
        ) : null}
        {template.upstream_changed ? (
          <Badge tone="vermilion">{t("companionAdmin.world.upstream")}</Badge>
        ) : null}
        {template.required_placeholders.length > 0 ? (
          <span className="ca-hint">
            {t("companionAdmin.templates.required", {
              names: template.required_placeholders
                .map((name) => `{${name}}`)
                .join(" "),
            })}
          </span>
        ) : null}
      </div>
      {!template.body ? (
        <p className="ca-hint">{t("companionAdmin.templates.noDefault")}</p>
      ) : null}
      <textarea
        className="input ca-template__body"
        rows={12}
        value={body}
        spellCheck={false}
        aria-label={t(
          `companionAdmin.templates.names.${template.template_key}` as TranslationKey,
        )}
        onChange={(event) => setBody(event.target.value)}
      />
      {missing.length > 0 ? (
        <p className="ca-lint" role="status">
          {t("companionAdmin.templates.missing", {
            names: missing.map((name) => `{${name}}`).join(" "),
          })}
        </p>
      ) : null}
      <div className="ca-actions">
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={
            update.isPending ||
            missing.length > 0 ||
            !body.trim() ||
            body === template.body
          }
          onClick={() =>
            void run(() =>
              update.mutateAsync({
                templateKey: template.template_key,
                data: { body },
                params: { locale: template.locale },
              }),
            )
          }
        >
          {t("companionAdmin.world.save")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={previewMutation.isPending}
          onClick={() =>
            void previewMutation
              .mutateAsync({
                data: {
                  template_key: template.template_key,
                  locale: template.locale,
                  body,
                },
              })
              .then(setPreview)
              .catch((caught: unknown) =>
                toast.error(
                  apiErrorMessage(caught, "companionAdmin.world.error"),
                ),
              )
          }
        >
          {t("companionAdmin.templates.preview")}
        </Button>
        {template.admin_modified ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={reset.isPending}
            onClick={() =>
              void run(() =>
                reset.mutateAsync({
                  templateKey: template.template_key,
                  params: { locale: template.locale },
                }),
              )
            }
          >
            {t("companionAdmin.world.reset")}
          </Button>
        ) : null}
      </div>
      {preview ? (
        <figure className="ca-preview">
          <figcaption>{t("companionAdmin.templates.previewNote")}</figcaption>
          <pre>{preview.rendered}</pre>
          {preview.unknown_placeholders.length > 0 ? (
            <p className="ca-lint">
              {t("companionAdmin.templates.unknown", {
                names: preview.unknown_placeholders
                  .map((name) => `{${name}}`)
                  .join(" "),
              })}
            </p>
          ) : null}
        </figure>
      ) : null}
    </div>
  );
}

function DraftForUser() {
  const { t } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const users = useListCompanionUserSummariesAdmin({ query: { retry: false } });
  const presets = useListCompanionPresetsAdmin({
    query: { retry: false, staleTime: 60_000 },
  });
  const generate = useGenerateCompanionStoryAdmin();
  const [userId, setUserId] = useState("");
  const [presetId, setPresetId] = useState("vellum");
  const account = (users.data ?? []).find(
    (row) => String(row.user_id) === userId,
  );
  return (
    <section className="ca-subsection">
      <h4>{t("companionAdmin.templates.draftFor")}</h4>
      <div className="ca-row">
        <label className="ca-field">
          <span>{t("companionAdmin.templates.draftPick")}</span>
          <select
            className="input"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
          >
            <option value="">—</option>
            {(users.data ?? []).map((row) => (
              <option key={row.user_id} value={row.user_id}>
                {row.display_name || row.username}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          <span>{t("companionAdmin.templates.draftCompanion")}</span>
          <select
            className="input"
            value={presetId}
            onChange={(event) => setPresetId(event.target.value)}
          >
            {(presets.data ?? []).map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.names.en ?? preset.id}
              </option>
            ))}
          </select>
        </label>
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={!account || generate.isPending}
          onClick={() =>
            void generate
              .mutateAsync({
                userId: Number(userId),
                data: { companion_ref: `preset:${presetId}` },
              })
              .then(() => {
                refresh();
                toast.success(
                  t("companionAdmin.templates.draftQueued", {
                    name: account?.display_name || account?.username || "",
                  }),
                );
              })
              .catch((caught: unknown) =>
                toast.error(
                  apiErrorMessage(caught, "companionAdmin.world.error"),
                ),
              )
          }
        >
          {t("companionAdmin.stories.generate")}
        </Button>
      </div>
    </section>
  );
}
