import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { clearLastChatConversation } from "../chat/session-storage";
import {
  getGetAuthStatusQueryKey,
  useGetAuthStatus,
  useImpersonateAccount,
  useLogin,
  useLogout,
  useSetupAccount,
  useStopImpersonation,
} from "../generated-apis-types";
import type {
  AuthResponseSchema,
  AuthStatusSchema,
  ImpersonationSchema,
  LoginSchema,
  SetupSchema,
  UserSchema,
} from "../generated-apis-types/schemas";
import { useI18n } from "../i18n";
import { translateApiError } from "../i18n/errors";
import {
  broadcastSessionTransition,
  subscribeToSessionTransitions,
} from "./session-transition";

interface AuthContextValue {
  readonly status: AuthStatusSchema | undefined;
  readonly user: UserSchema | null;
  readonly isLoading: boolean;
  readonly isAuthenticated: boolean;
  readonly role: UserSchema["role"] | null;
  readonly isRoot: boolean;
  readonly mustChangePassword: boolean;
  readonly requiresSetup: boolean;
  readonly isSubmitting: boolean;
  readonly error: string | null;
  readonly loadError: string | null;
  readonly retry: () => void;
  readonly login: (payload: LoginSchema) => Promise<void>;
  readonly setup: (payload: SetupSchema) => Promise<void>;
  readonly logout: () => Promise<void>;
  readonly impersonation: ImpersonationSchema | null;
  readonly isImpersonating: boolean;
  readonly impersonate: (userId: number) => Promise<void>;
  readonly stopImpersonation: (password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const UNAUTHORIZED_EVENT = "apsor-archive:unauthorized";
const AUTH_STATUS_KEY = getGetAuthStatusQueryKey();

function unauthenticatedStatus(): AuthStatusSchema {
  return {
    requires_setup: false,
    authenticated: false,
    user: null,
    impersonation: null,
  };
}

/** User + actor identity used to detect a session change in this tab. */
function sessionIdentity(
  status: AuthStatusSchema | undefined,
): string | null {
  if (!status?.authenticated || !status.user) {
    return null;
  }
  return `${status.user.user_id}:${status.impersonation?.actor_user_id ?? "none"}`;
}

function responseIdentity(response: AuthResponseSchema): string {
  return `${response.user.user_id}:${response.impersonation?.actor_user_id ?? "none"}`;
}

/**
 * Owns the session status and the setup/login/logout mutations. The gate above
 * every archive route reads this context, so a lost cookie returns the reader
 * to the login screen without a page reload.
 */
export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const sessionIdentityRef = useRef<string | null>(null);
  const unauthorizedHandledRef = useRef(false);
  const statusQuery = useGetAuthStatus({
    query: {
      retry: false,
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
  });

  const localizeError = useCallback(
    (caught: unknown): string => translateApiError(caught, t),
    [t],
  );

  // Keep the auth-status observer mounted while dropping private query data.
  // queryClient.clear() would detach that observer, so a later setQueryData
  // would not re-render AuthGate and a revoked session could leave the old
  // private page on screen. Remove everything except the auth-status query.
  const clearPrivateQueries = useCallback(() => {
    queryClient.removeQueries({
      predicate: (query) => query.queryKey[0] !== AUTH_STATUS_KEY[0],
    });
  }, [queryClient]);

  const markSignedIn = useCallback(
    (response: AuthResponseSchema) => {
      unauthorizedHandledRef.current = false;
      // The resume shortcut is shared across tabs; clear it before another
      // account can land on the previous account's conversation id.
      clearLastChatConversation();
      sessionIdentityRef.current = responseIdentity(response);
      // Never carry another session's private query data across a sign-in,
      // account switch, or impersonation transition. Query keys are not
      // user-scoped, so the old data must be removed before the new status.
      clearPrivateQueries();
      queryClient.setQueryData<AuthStatusSchema>(AUTH_STATUS_KEY, {
        requires_setup: false,
        authenticated: true,
        user: response.user,
        impersonation: response.impersonation ?? null,
      });
      // Other tabs reload; this acting tab keeps its navigation in flight.
      broadcastSessionTransition();
    },
    [clearPrivateQueries, queryClient],
  );

  const setupMutation = useSetupAccount({
    mutation: {
      onSuccess: (data) => markSignedIn(data),
    },
  });
  const loginMutation = useLogin({
    mutation: {
      onSuccess: (data) => markSignedIn(data),
    },
  });
  const impersonateMutation = useImpersonateAccount({
    mutation: {
      onSuccess: (data) => markSignedIn(data),
    },
  });
  const stopImpersonationMutation = useStopImpersonation({
    mutation: {
      onSuccess: (data) => markSignedIn(data),
    },
  });
  const logoutMutation = useLogout({
    mutation: {
      onSuccess: () => {
        unauthorizedHandledRef.current = true;
        clearLastChatConversation();
        sessionIdentityRef.current = null;
        clearPrivateQueries();
        queryClient.setQueryData<AuthStatusSchema>(
          AUTH_STATUS_KEY,
          unauthenticatedStatus(),
        );
        void statusQuery.refetch();
        broadcastSessionTransition();
      },
    },
  });

  useEffect(() => {
    const handleUnauthorized = () => {
      if (unauthorizedHandledRef.current) {
        return;
      }
      unauthorizedHandledRef.current = true;
      // A lost/disabled session must not leave the previous account's private
      // query cache behind. Keep the auth-status observer alive so setting the
      // unauthenticated snapshot actually re-renders AuthGate, then confirm
      // with the server (a fresh instance may need the setup screen again).
      const hadSession =
        sessionIdentityRef.current !== null ||
        (statusQuery.data?.authenticated ?? false);
      clearLastChatConversation();
      sessionIdentityRef.current = null;
      clearPrivateQueries();
      queryClient.setQueryData<AuthStatusSchema>(
        AUTH_STATUS_KEY,
        unauthenticatedStatus(),
      );
      void statusQuery.refetch();
      if (hadSession) {
        broadcastSessionTransition();
      }
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [clearPrivateQueries, queryClient, statusQuery]);

  // A status refetch can discover that another tab replaced the cookie. Drop
  // this tab's rows and confirm once; the ref is updated first so this cannot
  // loop on the follow-up fetch.
  useEffect(() => {
    const next = sessionIdentity(statusQuery.data);
    const previous = sessionIdentityRef.current;
    if (next === previous) {
      return;
    }
    sessionIdentityRef.current = next;
    if (next !== null) {
      unauthorizedHandledRef.current = false;
    }
    if (next === null) {
      if (previous !== null) {
        clearLastChatConversation();
        clearPrivateQueries();
      }
      return;
    }
    if (previous === null) {
      return;
    }
    clearLastChatConversation();
    clearPrivateQueries();
    void statusQuery.refetch();
  }, [clearPrivateQueries, statusQuery]);

  // A cookie change in another tab makes every local DOM/query snapshot stale.
  // The acting tab is excluded by the transition bus, so only observers reload.
  useEffect(() => {
    let reloadRequested = false;
    return subscribeToSessionTransitions(() => {
      if (reloadRequested) {
        return;
      }
      reloadRequested = true;
      window.location.reload();
    });
  }, []);

  const setup = useCallback(
    async (payload: SetupSchema) => {
      setError(null);
      try {
        await setupMutation.mutateAsync({ data: payload });
      } catch (caught) {
        setError(localizeError(caught));
      }
    },
    [localizeError, setupMutation],
  );

  const login = useCallback(
    async (payload: LoginSchema) => {
      setError(null);
      try {
        await loginMutation.mutateAsync({ data: payload });
      } catch (caught) {
        setError(localizeError(caught));
      }
    },
    [localizeError, loginMutation],
  );

  const logout = useCallback(async () => {
    setError(null);
    try {
      await logoutMutation.mutateAsync();
    } catch (caught) {
      setError(localizeError(caught));
    }
  }, [localizeError, logoutMutation]);

  // Impersonation transitions intentionally propagate failures to the caller.
  // The footer switcher and account cards show the localized API error in
  // place without losing the current session.
  const impersonate = useCallback(
    async (userId: number) => {
      await impersonateMutation.mutateAsync({ userId });
    },
    [impersonateMutation],
  );

  const stopImpersonation = useCallback(async (password: string) => {
    await stopImpersonationMutation.mutateAsync({ data: { password } });
  }, [stopImpersonationMutation]);

  const value = useMemo<AuthContextValue>(() => {
    const status = statusQuery.data;
    const user = status?.user ?? null;
    const impersonation = status?.impersonation ?? null;
    return {
      status,
      user,
      isLoading: statusQuery.isPending,
      isAuthenticated: status?.authenticated ?? false,
      role: user?.role ?? null,
      isRoot: user?.role === "root",
      mustChangePassword: user?.must_change_password ?? false,
      requiresSetup: status?.requires_setup ?? false,
      isSubmitting:
        setupMutation.isPending ||
        loginMutation.isPending ||
        logoutMutation.isPending ||
        impersonateMutation.isPending ||
        stopImpersonationMutation.isPending,
      error,
      loadError: statusQuery.error ? localizeError(statusQuery.error) : null,
      retry: () => {
        void statusQuery.refetch();
      },
      login,
      setup,
      logout,
      impersonation,
      isImpersonating: impersonation !== null,
      impersonate,
      stopImpersonation,
    };
  }, [
    error,
    impersonate,
    impersonateMutation.isPending,
    localizeError,
    login,
    loginMutation.isPending,
    logout,
    logoutMutation.isPending,
    setup,
    setupMutation.isPending,
    statusQuery,
    stopImpersonation,
    stopImpersonationMutation.isPending,
  ]);

  return <AuthContext value={value}>{children}</AuthContext>;
}

/** Reads the session state from any component below AuthProvider. */
export function useAuth(): AuthContextValue {
  const value = use(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return value;
}
