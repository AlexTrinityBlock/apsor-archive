import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useGetCompanionWorldDocAdmin,
  useListCompanionWorldDocRevisionsAdmin,
  useListCompanionWorldDocsAdmin,
  useResetCompanionWorldDocAdmin,
  useUpdateCompanionWorldDocAdmin,
} from "../../generated-apis-types";
import type {
  CompanionWorldDocSchema,
  CompanionWorldDocSummarySchema,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { lineDiff } from "../constellation";
import { useAdminRefresh } from "../hook/useAdminRefresh";

const REMARK_PLUGINS = [remarkGfm];
const DIFF_PREFIX = { add: "+ ", remove: "- ", same: "  " } as const;

function docLabel(
  doc: Pick<CompanionWorldDocSummarySchema, "doc_key" | "kind" | "title">,
  kindLabel: string,
): string {
  const tail = doc.doc_key.startsWith("character:")
    ? ` · ${doc.doc_key.slice(10)}`
    : "";
  return `${kindLabel}${tail}`;
}

/** The world bible and its companions: a markdown split editor with revisions. */
export function WorldDocEditor() {
  const { t } = useI18n();
  const docs = useListCompanionWorldDocsAdmin({ query: { retry: false } });
  const [selected, setSelected] = useState<string | null>(null);
  const list = docs.data ?? [];
  const current =
    selected ?? (list[0] ? `${list[0].doc_key}|${list[0].locale}` : null);

  if (docs.isPending)
    return <Loader label={t("companionAdmin.world.loading")} />;
  if (!current)
    return <p className="ca-empty">{t("companionAdmin.world.loadError")}</p>;
  const [docKey, locale] = current.split("|") as [
    string,
    "en" | "zh-TW" | "zh-CN",
  ];

  return (
    <div className="ca-docs">
      <nav className="ca-docs__nav" aria-label={t("companionAdmin.docs.pick")}>
        <ul>
          {list.map((doc) => {
            const id = `${doc.doc_key}|${doc.locale}`;
            return (
              <li key={id}>
                <button
                  type="button"
                  className={`ca-docs__item${id === current ? " is-active" : ""}`}
                  aria-current={id === current}
                  onClick={() => setSelected(id)}
                >
                  <span>
                    {docLabel(doc, t(`companionAdmin.docs.kinds.${doc.kind}`))}
                  </span>
                  <small>
                    {t(`companionAdmin.locales.${doc.locale}`)}
                    {doc.admin_modified
                      ? ` · ${t("companionAdmin.world.modified")}`
                      : ""}
                  </small>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <DocPane key={current} docKey={docKey} locale={locale} />
    </div>
  );
}

function DocPane({
  docKey,
  locale,
}: {
  readonly docKey: string;
  readonly locale: "en" | "zh-TW" | "zh-CN";
}) {
  const { t } = useI18n();
  const doc = useGetCompanionWorldDocAdmin(
    docKey,
    { locale },
    { query: { retry: false } },
  );
  if (doc.isPending)
    return <Loader label={t("companionAdmin.world.loading")} />;
  if (!doc.data)
    return <p className="ca-empty">{t("companionAdmin.world.loadError")}</p>;
  return <DocForm key={doc.data.version} doc={doc.data} />;
}

function DocForm({ doc }: { readonly doc: CompanionWorldDocSchema }) {
  const { t, formatDateTime } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const [body, setBody] = useState(doc.body_md);
  const [view, setView] = useState<"split" | "edit" | "preview">("split");
  const [compareId, setCompareId] = useState<number | null>(null);
  const update = useUpdateCompanionWorldDocAdmin();
  const reset = useResetCompanionWorldDocAdmin();
  const revisions = useListCompanionWorldDocRevisionsAdmin(
    doc.doc_key,
    { locale: doc.locale },
    {
      query: { retry: false },
    },
  );
  const compare =
    (revisions.data ?? []).find((revision) => revision.id === compareId) ??
    null;
  const dirty = body !== doc.body_md;
  const viewLabels = {
    edit: t("companionAdmin.docs.edit"),
    preview: t("companionAdmin.docs.preview"),
    split: [
      t("companionAdmin.docs.edit"),
      t("companionAdmin.docs.preview"),
    ].join(" · "),
  } as const;

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
    <section className="ca-docs__pane" aria-label={doc.title}>
      <header className="ca-docs__head">
        <div>
          <h3>{doc.title}</h3>
          <p className="ca-hint">
            {t("companionAdmin.docs.version", { version: String(doc.version) })}
            {doc.updated_at ? ` · ${formatDateTime(doc.updated_at)}` : ""}
          </p>
        </div>
        <div className="ca-row">
          {doc.admin_modified ? (
            <Badge tone="ochre">{t("companionAdmin.world.modified")}</Badge>
          ) : null}
          {doc.upstream_changed ? (
            <Badge tone="vermilion">{t("companionAdmin.world.upstream")}</Badge>
          ) : null}
          <div
            className="ca-seg"
            role="group"
            aria-label={t("companionAdmin.docs.preview")}
          >
            {(["edit", "split", "preview"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                className={view === mode ? "is-on" : ""}
                aria-pressed={view === mode}
                onClick={() => setView(mode)}
              >
                {viewLabels[mode]}
              </button>
            ))}
          </div>
        </div>
      </header>
      <div className={`ca-docs__split ca-docs__split--${view}`}>
        {view !== "preview" ? (
          <textarea
            className="input ca-docs__editor"
            value={body}
            spellCheck={false}
            aria-label={t("companionAdmin.docs.edit")}
            onChange={(event) => setBody(event.target.value)}
          />
        ) : null}
        {view !== "edit" ? (
          <div className="ca-docs__preview prose">
            <ReactMarkdown remarkPlugins={REMARK_PLUGINS}>{body}</ReactMarkdown>
          </div>
        ) : null}
      </div>
      <div className="ca-actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          disabled={!dirty || update.isPending}
          onClick={() =>
            void run(() =>
              update.mutateAsync({
                docKey: doc.doc_key,
                data: { body_md: body, version: doc.version },
                params: { locale: doc.locale },
              }),
            )
          }
        >
          {t("companionAdmin.world.save")}
        </Button>
        {doc.admin_modified ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={reset.isPending}
            onClick={() =>
              void run(() =>
                reset.mutateAsync({
                  docKey: doc.doc_key,
                  params: { locale: doc.locale },
                }),
              )
            }
          >
            {t("companionAdmin.world.reset")}
          </Button>
        ) : null}
      </div>
      <details className="ca-revisions">
        <summary>{t("companionAdmin.docs.revisions")}</summary>
        {(revisions.data ?? []).length === 0 ? (
          <p className="ca-empty">{t("companionAdmin.docs.revisionsNone")}</p>
        ) : (
          <ul>
            {(revisions.data ?? []).map((revision) => (
              <li key={revision.id}>
                <span>
                  {t("companionAdmin.docs.version", {
                    version: String(revision.version),
                  })}{" "}
                  · {formatDateTime(revision.created_at)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setCompareId(compareId === revision.id ? null : revision.id)
                  }
                >
                  {t("companionAdmin.docs.compare")}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {compare ? (
          <pre className="ca-diff">
            {lineDiff(compare.body_md, body).map((line, index) => (
              <span key={index} className={`ca-diff__${line.kind}`}>
                {DIFF_PREFIX[line.kind]}
                {line.text}
                {"\n"}
              </span>
            ))}
          </pre>
        ) : null}
      </details>
    </section>
  );
}
