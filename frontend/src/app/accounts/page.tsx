import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../component/Button";
import { EmptyState } from "../component/EmptyState";
import { Icon } from "../component/Icon";
import { Loader } from "../component/Loader";
import { PageHeader } from "../component/PageHeader";
import { Panel } from "../component/Panel";
import { useToast } from "../component/Toast";
import {
  getGetMyModelAssignmentQueryKey,
  getListAccountsQueryKey,
  getListModelAssignmentsQueryKey,
  useCreateAccount,
  useDisableAccount,
  useEnableAccount,
  useListAccounts,
  useListModelAssignments,
  useResetAccountPassword,
  useResetAccountQuota,
  useResetModelAssignment,
  useTopUpAccountQuota,
  useUpdateAccountQuota,
  useUpdateModelAssignment,
} from "../generated-apis-types";
import type {
  AccountCreateSchema,
  AccountQuotaSchemaCategory,
  AccountSchema,
  ModelAssignmentSchema,
  ModelAssignmentUpdateSchema,
} from "../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../i18n";
import { AccountCard } from "./component/AccountCard";
import {
  ConfirmAccountActionDialog,
  type AccountAction,
} from "./component/ConfirmAccountActionDialog";
import { CreateAccountDialog } from "./component/CreateAccountDialog";
import { ModelDialog } from "./component/ModelDialog";
import { QuotaDialog } from "./component/QuotaDialog";
import { SystemNoticesPanel } from "./component/SystemNoticesPanel";
import { TemporaryPasswordDialog } from "./component/TemporaryPasswordDialog";
import "./accounts.css";

type DialogState =
  | { readonly kind: "create" }
  | {
      readonly kind: "confirm";
      readonly action: AccountAction;
      readonly account: AccountSchema;
    }
  | {
      readonly kind: "temporary";
      readonly account: AccountSchema;
      readonly password: string;
    }
  | { readonly kind: "quota"; readonly account: AccountSchema }
  | {
      readonly kind: "model";
      readonly account: AccountSchema;
      readonly assignment: ModelAssignmentSchema;
    }
  | null;

function rootFirst(items: readonly AccountSchema[]): AccountSchema[] {
  return [...items].sort(
    (left, right) =>
      Number(right.role === "root") - Number(left.role === "root"),
  );
}

/**
 * Root-only account directory. Every mutation invalidates the list query, and
 * a one-time temporary password never leaves this component's local state.
 */
export function AccountsPage() {
  const { t, formatNumber } = useI18n();
  const { user, impersonate } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const [dialog, setDialog] = useState<DialogState>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [impersonationPending, setImpersonationPending] = useState(false);

  const query = useListAccounts({
    query: { retry: false, staleTime: 15_000 },
  });
  const assignmentsQuery = useListModelAssignments({
    query: { retry: false, staleTime: 15_000 },
  });
  const createMutation = useCreateAccount();
  const disableMutation = useDisableAccount();
  const enableMutation = useEnableAccount();
  const resetMutation = useResetAccountPassword();
  const updateQuotaMutation = useUpdateAccountQuota();
  const topUpQuotaMutation = useTopUpAccountQuota();
  const resetQuotaMutation = useResetAccountQuota();
  const updateModelMutation = useUpdateModelAssignment();
  const resetModelMutation = useResetModelAssignment();

  const accounts = rootFirst(query.data?.items ?? []);
  const assignmentsByUser = new Map(
    (assignmentsQuery.data?.items ?? []).map((item) => [item.user_id, item]),
  );
  const mutationPending =
    createMutation.isPending ||
    disableMutation.isPending ||
    enableMutation.isPending ||
    resetMutation.isPending ||
    updateQuotaMutation.isPending ||
    topUpQuotaMutation.isPending ||
    resetQuotaMutation.isPending ||
    updateModelMutation.isPending ||
    resetModelMutation.isPending ||
    impersonationPending;

  const invalidateAccounts = () => {
    void queryClient.invalidateQueries({
      queryKey: getListAccountsQueryKey(),
    });
  };

  const invalidateModelAssignments = () => {
    void queryClient.invalidateQueries({
      queryKey: getListModelAssignmentsQueryKey(),
    });
    void queryClient.invalidateQueries({
      queryKey: getGetMyModelAssignmentQueryKey(),
    });
    invalidateAccounts();
  };

  const openCreate = () => {
    setDialogError(null);
    setDialog({ kind: "create" });
  };

  const openAction = (action: AccountAction, account: AccountSchema) => {
    setDialogError(null);
    setDialog({ kind: "confirm", action, account });
  };

  const openQuotas = (account: AccountSchema) => {
    setDialogError(null);
    setDialog({ kind: "quota", account });
  };

  const openModel = (account: AccountSchema) => {
    const assignment = assignmentsByUser.get(account.user_id);
    if (assignment === undefined) {
      return;
    }
    setDialogError(null);
    setDialog({ kind: "model", account, assignment });
  };

  const closeDialog = () => {
    if (mutationPending) {
      return;
    }
    setDialog(null);
    setDialogError(null);
  };

  const handleCreate = async (payload: AccountCreateSchema) => {
    if (createMutation.isPending) {
      return;
    }
    setDialogError(null);
    try {
      const result = await createMutation.mutateAsync({ data: payload });
      createMutation.reset();
      invalidateAccounts();
      setDialog({
        kind: "temporary",
        account: result.user,
        password: result.temporary_password,
      });
      toast.success(t("core.accounts.createSuccess"));
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.error"));
    }
  };

  const handleConfirm = async () => {
    if (dialog?.kind !== "confirm" || mutationPending) {
      return;
    }
    const { action, account } = dialog;
    setDialogError(null);
    if (action === "impersonate") {
      setImpersonationPending(true);
      try {
        await impersonate(account.user_id);
        setDialog(null);
        navigate("/chat");
      } catch (caught) {
        setDialogError(
          apiErrorMessage(caught, "core.accounts.impersonateError"),
        );
      } finally {
        setImpersonationPending(false);
      }
      return;
    }
    try {
      if (action === "disable") {
        await disableMutation.mutateAsync({ userId: account.user_id });
        disableMutation.reset();
        invalidateAccounts();
        toast.success(t("core.accounts.disableSuccess"));
        setDialog(null);
        return;
      }
      if (action === "enable") {
        await enableMutation.mutateAsync({ userId: account.user_id });
        enableMutation.reset();
        invalidateAccounts();
        toast.success(t("core.accounts.enableSuccess"));
        setDialog(null);
        return;
      }
      const result = await resetMutation.mutateAsync({
        userId: account.user_id,
      });
      resetMutation.reset();
      invalidateAccounts();
      setDialog({
        kind: "temporary",
        account: result.user,
        password: result.temporary_password,
      });
      toast.success(t("core.accounts.resetSuccess"));
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.error"));
    }
  };

  const handleQuotaSave = async (
    category: AccountQuotaSchemaCategory,
    enabled: boolean,
    granted: number | null,
  ) => {
    if (dialog?.kind !== "quota" || mutationPending) {
      return;
    }
    setDialogError(null);
    try {
      const result = await updateQuotaMutation.mutateAsync({
        userId: dialog.account.user_id,
        category,
        data: { enabled, granted },
      });
      updateQuotaMutation.reset();
      invalidateAccounts();
      setDialog({ kind: "quota", account: result });
      toast.success(t("core.accounts.quotaSaveSuccess"));
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.quotaError"));
    }
  };

  const handleQuotaTopUp = async (
    category: AccountQuotaSchemaCategory,
    amount: number,
  ) => {
    if (dialog?.kind !== "quota" || mutationPending) {
      return;
    }
    setDialogError(null);
    try {
      const result = await topUpQuotaMutation.mutateAsync({
        userId: dialog.account.user_id,
        category,
        data: { amount },
      });
      topUpQuotaMutation.reset();
      invalidateAccounts();
      setDialog({ kind: "quota", account: result });
      toast.success(t("core.accounts.quotaTopUpSuccess"));
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.quotaError"));
    }
  };

  const handleQuotaReset = async (
    category: AccountQuotaSchemaCategory,
    granted: number | null,
  ) => {
    if (dialog?.kind !== "quota" || mutationPending) {
      return;
    }
    setDialogError(null);
    try {
      const result = await resetQuotaMutation.mutateAsync({
        userId: dialog.account.user_id,
        category,
        data: { granted },
      });
      resetQuotaMutation.reset();
      invalidateAccounts();
      setDialog({ kind: "quota", account: result });
      toast.success(t("core.accounts.quotaResetSuccess"));
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.quotaError"));
    }
  };

  const handleModelSave = async (payload: ModelAssignmentUpdateSchema) => {
    if (dialog?.kind !== "model" || mutationPending) {
      return;
    }
    setDialogError(null);
    try {
      await updateModelMutation.mutateAsync({
        userId: dialog.account.user_id,
        data: payload,
      });
      updateModelMutation.reset();
      invalidateModelAssignments();
      toast.success(t("core.accounts.modelSaveSuccess"));
      setDialog(null);
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.modelError"));
    }
  };

  const handleModelReset = async () => {
    if (dialog?.kind !== "model" || mutationPending) {
      return;
    }
    setDialogError(null);
    try {
      await resetModelMutation.mutateAsync({ userId: dialog.account.user_id });
      resetModelMutation.reset();
      invalidateModelAssignments();
      toast.success(t("core.accounts.modelResetSuccess"));
      setDialog(null);
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.modelError"));
    }
  };

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
      <ul className="accounts-list">
        {accounts.map((account) => (
          <li key={account.user_id}>
            <AccountCard
              account={account}
              currentUserId={user?.user_id ?? null}
              assignment={assignmentsByUser.get(account.user_id) ?? null}
              assignmentLoading={assignmentsQuery.isPending}
              assignmentError={assignmentsQuery.isError}
              onAction={openAction}
              onManageQuotas={openQuotas}
              onManageModel={openModel}
            />
          </li>
        ))}
      </ul>
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
                { count: formatNumber(accounts.length) },
              )}
            </span>
          ) : undefined
        }
        actions={
          <Button type="button" variant="primary" size="sm" onClick={openCreate}>
            <Icon name="plus" size={14} />
            {t("core.accounts.create")}
          </Button>
        }
      />
      <SystemNoticesPanel />
      {body}

      {dialog?.kind === "create" ? (
        <CreateAccountDialog
          onClose={closeDialog}
          onSubmit={(payload) => void handleCreate(payload)}
          submitting={createMutation.isPending}
          error={dialogError}
        />
      ) : null}

      {dialog?.kind === "confirm" ? (
        <ConfirmAccountActionDialog
          action={dialog.action}
          account={dialog.account}
          onClose={closeDialog}
          onConfirm={() => void handleConfirm()}
          submitting={mutationPending}
          error={dialogError}
        />
      ) : null}

      {dialog?.kind === "temporary" ? (
        <TemporaryPasswordDialog
          account={dialog.account}
          password={dialog.password}
          onClose={closeDialog}
        />
      ) : null}

      {dialog?.kind === "quota" ? (
        <QuotaDialog
          account={dialog.account}
          onClose={closeDialog}
          onSave={(category, enabled, granted) =>
            void handleQuotaSave(category, enabled, granted)
          }
          onTopUp={(category, amount) =>
            void handleQuotaTopUp(category, amount)
          }
          onReset={(category, granted) =>
            void handleQuotaReset(category, granted)
          }
          submitting={mutationPending}
          error={dialogError}
        />
      ) : null}
      {dialog?.kind === "model" ? (
        <ModelDialog
          account={dialog.account}
          assignment={dialog.assignment}
          onClose={closeDialog}
          onSave={(payload) => void handleModelSave(payload)}
          onReset={() => void handleModelReset()}
          submitting={mutationPending}
          error={dialogError}
        />
      ) : null}
    </div>
  );
}
