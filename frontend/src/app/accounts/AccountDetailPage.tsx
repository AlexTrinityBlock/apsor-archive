import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { UserCompanionTab } from "../companion-admin/component/UserCompanionTab";
import { ButtonLink } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { useI18n } from "../i18n";
import { AccountCard } from "./component/AccountCard";
import { useAccountsWorkspace } from "./hook/useAccountsWorkspace";
import "./accounts.css";

const TABS = ["account", "models", "companion"] as const;
type DetailTab = (typeof TABS)[number];

function isTab(value: string | null): value is DetailTab {
  return value !== null && (TABS as readonly string[]).includes(value);
}

/**
 * One account, in three tabs: the account card and its actions, its model and
 * quota editors inline, and root's white-box view of its companions.
 */
export function AccountDetailPage() {
  const { t } = useI18n();
  const { userId: rawId } = useParams<{ userId: string }>();
  const [params, setParams] = useSearchParams();
  const userId = Number.parseInt(rawId ?? "", 10);
  const tab: DetailTab = isTab(params.get("tab"))
    ? (params.get("tab") as DetailTab)
    : "account";
  const workspace = useAccountsWorkspace();
  const account =
    workspace.accounts.find((item) => item.user_id === userId) ?? null;
  const [editor, setEditor] = useState<"model" | "quota">("model");
  const { openModel, openQuotas, dialog, assignmentsByUser } = workspace;
  const hasAssignment =
    account !== null && assignmentsByUser.has(account.user_id);
  const inlineKind =
    dialog && "inline" in dialog && dialog.inline ? dialog.kind : null;

  // Keep the inline editor in step with the selected tab and sub-view.
  useEffect(() => {
    if (tab !== "models" || account === null) return;
    if (editor === "model" && hasAssignment && inlineKind !== "model") {
      openModel(account, true);
    } else if (editor === "quota" && inlineKind !== "quota") {
      openQuotas(account, true);
    }
  }, [tab, editor, account, hasAssignment, inlineKind, openModel, openQuotas]);

  if (workspace.query.isPending) {
    return (
      <div className="content-container accounts-page">
        <Loader label={t("core.accounts.loading")} />
      </div>
    );
  }
  if (!Number.isFinite(userId) || account === null) {
    return (
      <div className="content-container accounts-page">
        <EmptyState
          icon="users"
          eyebrow={t("core.accounts.eyebrow")}
          title={t("companionAdmin.detail.notFound")}
          description=""
        />
        <ButtonLink to="/accounts" variant="ghost" size="sm">
          {t("companionAdmin.detail.back")}
        </ButtonLink>
      </div>
    );
  }

  const name = account.display_name || account.username;
  return (
    <div className="content-container accounts-page accounts-detail">
      <PageHeader
        eyebrow={t("core.accounts.eyebrow")}
        title={name}
        description={`@${account.username} · ${account.role}`}
        actions={
          <ButtonLink to="/accounts" variant="ghost" size="sm">
            <Icon name="users" size={14} />
            {t("companionAdmin.detail.back")}
          </ButtonLink>
        }
      />
      <div
        className="ca-sections"
        role="tablist"
        aria-label={t("companionAdmin.detail.tabsLabel")}
      >
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={tab === item}
            className={`ca-sections__tab${tab === item ? " is-active" : ""}`}
            onClick={() => setParams({ tab: item }, { replace: true })}
          >
            {t(`companionAdmin.detail.tabs.${item}`)}
          </button>
        ))}
      </div>
      <div className="accounts-detail__body" role="tabpanel">
        {tab === "account" ? (
          <AccountCard
            account={account}
            currentUserId={workspace.user?.user_id ?? null}
            assignment={assignmentsByUser.get(account.user_id) ?? null}
            assignmentLoading={workspace.assignmentsQuery.isPending}
            assignmentError={workspace.assignmentsQuery.isError}
            onAction={workspace.openAction}
            onManageQuotas={(target) => {
              setEditor("quota");
              setParams({ tab: "models" }, { replace: true });
              openQuotas(target, true);
            }}
            onManageModel={(target) => {
              setEditor("model");
              setParams({ tab: "models" }, { replace: true });
              openModel(target, true);
            }}
          />
        ) : null}
        {tab === "models" ? (
          <div className="accounts-detail__models">
            <p className="ca-hint">{t("companionAdmin.detail.modelsHint")}</p>
            <div
              className="ca-seg"
              role="group"
              aria-label={t("companionAdmin.detail.tabs.models")}
            >
              <button
                type="button"
                className={editor === "model" ? "is-on" : ""}
                aria-pressed={editor === "model"}
                onClick={() => setEditor("model")}
              >
                {t("companionAdmin.detail.showModels")}
              </button>
              <button
                type="button"
                className={editor === "quota" ? "is-on" : ""}
                aria-pressed={editor === "quota"}
                onClick={() => setEditor("quota")}
              >
                {t("companionAdmin.detail.showQuotas")}
              </button>
            </div>
            {editor === "model" && !hasAssignment ? (
              <p className="ca-hint">
                {t("companionAdmin.detail.modelUnavailable")}
              </p>
            ) : null}
            {workspace.inlineEditor}
          </div>
        ) : null}
        {tab === "companion" ? (
          <UserCompanionTab userId={account.user_id} />
        ) : null}
      </div>
      {workspace.modalDialogs}
    </div>
  );
}
