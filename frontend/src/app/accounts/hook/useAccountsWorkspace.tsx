import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { useToast } from "../../component/Toast";
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
} from "../../generated-apis-types";
import type {
  AccountCreateSchema,
  AccountQuotaSchemaCategory,
  AccountSchema,
  ModelAssignmentSchema,
  ModelAssignmentUpdateSchema,
} from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import {
  ConfirmAccountActionDialog,
  type AccountAction,
} from "../component/ConfirmAccountActionDialog";
import { CreateAccountDialog } from "../component/CreateAccountDialog";
import { ModelDialog } from "../component/ModelDialog";
import { QuotaDialog } from "../component/QuotaDialog";
import { TemporaryPasswordDialog } from "../component/TemporaryPasswordDialog";

export type AccountDialogState =
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
  | {
      readonly kind: "quota";
      readonly account: AccountSchema;
      readonly inline?: boolean;
    }
  | {
      readonly kind: "model";
      readonly account: AccountSchema;
      readonly assignment: ModelAssignmentSchema;
      readonly inline?: boolean;
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

/**
 * State, mutations, and dialogs shared by the account directory and the
 * account detail page. Quota and model editors can render inline (detail
 * page tabs) or as modals (directory).
 */
export function useAccountsWorkspace() {
  const { t } = useI18n();
  const { user, impersonate } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const [dialog, setDialog] = useState<AccountDialogState>(null);
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

  const openQuotas = (account: AccountSchema, inline = false) => {
    setDialogError(null);
    setDialog({ kind: "quota", account, inline });
  };

  const openModel = (account: AccountSchema, inline = false) => {
    const assignment = assignmentsByUser.get(account.user_id);
    if (assignment === undefined) {
      return;
    }
    setDialogError(null);
    setDialog({ kind: "model", account, assignment, inline });
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
      setDialog({ kind: "quota", account: result, inline: dialog.inline });
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
      setDialog({ kind: "quota", account: result, inline: dialog.inline });
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
      setDialog({ kind: "quota", account: result, inline: dialog.inline });
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
      setDialog(dialog.inline ? dialog : null);
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
      setDialog(dialog.inline ? dialog : null);
    } catch (caught) {
      setDialogError(apiErrorMessage(caught, "core.accounts.modelError"));
    }
  };

  const modalDialogs = (
    <>
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

      {dialog?.kind === "quota" && !dialog.inline ? (
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
      {dialog?.kind === "model" && !dialog.inline ? (
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
    </>
  );

  const inlineEditor = (
    <>
      {dialog?.kind === "quota" && dialog.inline ? (
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
          inline
        />
      ) : null}
      {dialog?.kind === "model" && dialog.inline ? (
        <ModelDialog
          account={dialog.account}
          assignment={
            assignmentsByUser.get(dialog.account.user_id) ?? dialog.assignment
          }
          onClose={closeDialog}
          onSave={(payload) => void handleModelSave(payload)}
          onReset={() => void handleModelReset()}
          submitting={mutationPending}
          error={dialogError}
          inline
        />
      ) : null}
    </>
  );

  return {
    query,
    assignmentsQuery,
    accounts,
    assignmentsByUser,
    user,
    dialog,
    openCreate,
    openAction,
    openQuotas,
    openModel,
    closeDialog,
    modalDialogs,
    inlineEditor,
  };
}
