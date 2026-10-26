import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  getGetAuthStatusQueryKey,
  useGetAuthStatus,
  useLogin,
  useLogout,
  useSetupAccount,
} from "../generated-apis-types";
import type {
  AuthStatusSchema,
  LoginSchema,
  SetupSchema,
  UserSchema,
} from "../generated-apis-types/schemas";
import { useI18n } from "../i18n";
import { translateApiError } from "../i18n/errors";

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
}

const AuthContext = createContext<AuthContextValue | null>(null);

const UNAUTHORIZED_EVENT = "apsor-archive:unauthorized";
const AUTH_STATUS_KEY = getGetAuthStatusQueryKey();

function unauthenticatedStatus(): AuthStatusSchema {
  return { requires_setup: false, authenticated: false, user: null };
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
    (user: UserSchema) => {
      // Never carry another session's private query data across a sign-in.
      // Query keys are not user-scoped, so the old data must be removed.
      clearPrivateQueries();
      queryClient.setQueryData<AuthStatusSchema>(AUTH_STATUS_KEY, {
        requires_setup: false,
        authenticated: true,
        user,
      });
    },
    [clearPrivateQueries, queryClient],
  );

  const setupMutation = useSetupAccount({
    mutation: {
      onSuccess: (data) => markSignedIn(data.user),
    },
  });
  const loginMutation = useLogin({
    mutation: {
      onSuccess: (data) => markSignedIn(data.user),
    },
  });
  const logoutMutation = useLogout({
    mutation: {
      onSuccess: () => {
        clearPrivateQueries();
        queryClient.setQueryData<AuthStatusSchema>(
          AUTH_STATUS_KEY,
          unauthenticatedStatus(),
        );
        void statusQuery.refetch();
      },
    },
  });
  useEffect(() => {
    const handleUnauthorized = () => {
      // A lost/disabled session must not leave the previous account's private
      // query cache behind. Keep the auth-status observer alive so setting the
      // unauthenticated snapshot actually re-renders AuthGate, then confirm
      // with the server (a fresh instance may need the setup screen again).
      clearPrivateQueries();
      queryClient.setQueryData<AuthStatusSchema>(
        AUTH_STATUS_KEY,
        unauthenticatedStatus(),
      );
      void statusQuery.refetch();
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [clearPrivateQueries, queryClient, statusQuery]);

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

  const value = useMemo<AuthContextValue>(() => {
    const status = statusQuery.data;
    const user = status?.user ?? null;
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
        setupMutation.isPending || loginMutation.isPending || logoutMutation.isPending,
      error,
      loadError: statusQuery.error ? localizeError(statusQuery.error) : null,
      retry: () => {
        void statusQuery.refetch();
      },
      login,
      setup,
      logout,
    };
  }, [
    error,
    localizeError,
    login,
    loginMutation.isPending,
    logout,
    logoutMutation.isPending,
    setup,
    setupMutation.isPending,
    statusQuery,
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
