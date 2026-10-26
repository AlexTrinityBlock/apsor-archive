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
  getListAccountsQueryKey,
  useCreateAccount,
  useDisableAccount,
  useEnableAccount,
  useListAccounts,
  useResetAccountPassword,
} from "../generated-apis-types";
import type {
  AccountCreateSchema,
  AccountSchema,
} from "../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../i18n";
import { AccountCard } from "./component/AccountCard";
import {
  ConfirmAccountActionDialog,
  type AccountAction,
} from "./component/ConfirmAccountActionDialog";
import { CreateAccountDialog } from "./component/CreateAccountDialog";
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
  const createMutation = useCreateAccount();
  const disableMutation = useDisableAccount();
  const enableMutation = useEnableAccount();
  const resetMutation = useResetAccountPassword();

  const accounts = rootFirst(query.data?.items ?? []);
  const mutationPending =
    createMutation.isPending ||
    disableMutation.isPending ||
    enableMutation.isPending ||
    resetMutation.isPending ||
    impersonationPending;

  const invalidateAccounts = () => {
    void queryClient.invalidateQueries({
      queryKey: getListAccountsQueryKey(),
    });
  };

  const openCreate = () => {
    setDialogError(null);
    setDialog({ kind: "create" });
  };

  const openAction = (action: AccountAction, account: AccountSchema) => {
    setDialogError(null);
    setDialog({ kind: "confirm", action, account });
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
              onAction={openAction}
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
    </div>
  );
}
