import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  matchesDirectory,
  sparklinePoints,
  type DirectoryFilter,
} from "../companion-admin/constellation";
import { Button, ButtonLink } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useListCompanionUserSummariesAdmin } from "../generated-apis-types";
import type { CompanionUserSummarySchema } from "../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../i18n";
import { AccountCard } from "./component/AccountCard";
import { SystemNoticesPanel } from "./component/SystemNoticesPanel";
import { useAccountsWorkspace } from "./hook/useAccountsWorkspace";
import "./accounts.css";

const FILTERS: readonly DirectoryFilter[] = [
  "all",
  "root",
  "active",
  "disabled",
  "companion",
];

/**
 * Root-only account directory: search and filter accounts, glance at their
 * companion activity, and open an account's detail page. Every mutation
 * invalidates the list query, and a one-time temporary password never leaves
 * the workspace hook's local state.
 */
export function AccountsPage() {
  const { t, formatNumber } = useI18n();
  const apiErrorMessage = useApiErrorMessage();
  const workspace = useAccountsWorkspace();
  const { query, assignmentsQuery, accounts, assignmentsByUser, user } =
    workspace;
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<DirectoryFilter>("all");
  const summaries = useListCompanionUserSummariesAdmin({
    query: { retry: false, staleTime: 30_000 },
  });
  const summaryByUser = useMemo(
    () =>
      new Map<number, CompanionUserSummarySchema>(
        (summaries.data ?? []).map((row) => [row.user_id, row]),
      ),
    [summaries.data],
  );
  const visible = accounts.filter((account) =>
    matchesDirectory(
      account,
      search,
      filter,
      (summaryByUser.get(account.user_id)?.told_count ?? 0) > 0,
    ),
  );

  let body: ReactNode;
  if (query.isPending) {
    body = (
      <Panel tone="plain" className="accounts-state">
        <div className="accounts-state__loading">
          <Loader label={t("core.accounts.loading")} />
        </div>
      </Panel>
    );
  } else if (query.isError) {
    body = (
      <Panel tone="plain" className="accounts-state" role="alert">
        <div className="accounts-state__error">
          <span className="accounts-state__icon" aria-hidden="true">
            <Icon name="info" size={18} />
          </span>
          <div className="accounts-state__copy">
            <p className="eyebrow">{t("core.queryState.readInterrupted")}</p>
            <h2>{t("core.queryState.didNotAnswer")}</h2>
            <p>{apiErrorMessage(query.error, "core.accounts.error")}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
            >
              <Icon name="ring" size={14} />
              {query.isFetching
                ? t("core.common.retrying")
                : t("core.common.retry")}
            </Button>
          </div>
        </div>
      </Panel>
    );
  } else if (accounts.length === 0) {
    body = (
      <EmptyState
        icon="users"
        eyebrow={t("core.accounts.eyebrow")}
        title={t("core.accounts.empty")}
        description={t("core.accounts.emptyDescription")}
      />
    );
  } else {
    body = (
      <>
        <div className="accounts-directory-tools">
          <label className="accounts-directory-tools__search">
            <span className="visually-hidden">
              {t("companionAdmin.directory.searchLabel")}
            </span>
            <Icon name="search" size={14} />
            <input
              type="search"
              className="input"
              value={search}
              placeholder={t("companionAdmin.directory.searchPlaceholder")}
              aria-label={t("companionAdmin.directory.searchLabel")}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div
            className="accounts-directory-tools__filters"
            role="group"
            aria-label={t("companionAdmin.directory.filterLabel")}
          >
            {FILTERS.map((item) => (
              <button
                key={item}
                type="button"
                className={`accounts-filter${filter === item ? " is-on" : ""}`}
                aria-pressed={filter === item}
                onClick={() => setFilter(item)}
              >
                {t(`companionAdmin.directory.filters.${item}`)}
              </button>
            ))}
          </div>
        </div>
        {visible.length === 0 ? (
          <p className="accounts-directory-empty">
            {t("companionAdmin.directory.noMatch")}
          </p>
        ) : (
          <ul className="accounts-list">
            {visible.map((account) => {
              const summary = summaryByUser.get(account.user_id);
              const activity = summary?.activity ?? [];
              const active = activity.some((value) => value > 0);
              return (
                <li key={account.user_id} className="accounts-list__item">
                  <AccountCard
                    account={account}
                    currentUserId={user?.user_id ?? null}
                    assignment={assignmentsByUser.get(account.user_id) ?? null}
                    assignmentLoading={assignmentsQuery.isPending}
                    assignmentError={assignmentsQuery.isError}
                    onAction={workspace.openAction}
                    onManageQuotas={(target) => workspace.openQuotas(target)}
                    onManageModel={(target) => workspace.openModel(target)}
                  />
                  <div className="accounts-companion-strip">
                    <span
                      className="accounts-companion-strip__spark"
                      title={t("companionAdmin.directory.activityLabel")}
                    >
                      <svg
                        viewBox="0 0 72 18"
                        width={72}
                        height={18}
                        aria-hidden="true"
                      >
                        <polyline points={sparklinePoints(activity)} />
                      </svg>
                      <span>
                        {active
                          ? t("companionAdmin.directory.told", {
                              count: formatNumber(summary?.told_count ?? 0),
                            })
                          : t("companionAdmin.directory.activityNone")}
                      </span>
                    </span>
                    <Link
                      className="accounts-companion-strip__open"
                      to={`/accounts/${account.user_id}`}
                    >
                      {t("companionAdmin.directory.open")}
                      <Icon name="arrow-right" size={13} />
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </>
    );
  }

  return (
    <div className="content-container accounts-page">
      <PageHeader
        eyebrow={t("core.accounts.eyebrow")}
        title={t("core.accounts.title")}
        description={t("core.accounts.description")}
        meta={
          query.data ? (
            <span>
              {t(
                accounts.length === 1
                  ? "core.accounts.countOne"
                  : "core.accounts.countOther",
                {
                  count: formatNumber(accounts.length),
                },
              )}
            </span>
          ) : undefined
        }
        actions={
          <>
            <ButtonLink to="/accounts/world" variant="ghost" size="sm">
              <Icon name="companion" size={14} />
              {t("companionAdmin.directory.world")}
            </ButtonLink>
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={workspace.openCreate}
            >
              <Icon name="plus" size={14} />
              {t("core.accounts.create")}
            </Button>
          </>
        }
      />
      <SystemNoticesPanel />
      {body}
      {workspace.modalDialogs}
    </div>
  );
}
