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

import { ApiError } from "../../apis/fetch-client";
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

interface AuthContextValue {
  readonly status: AuthStatusSchema | undefined;
  readonly user: UserSchema | null;
  readonly isLoading: boolean;
  readonly isAuthenticated: boolean;
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

const UNAUTHORIZED_EVENT = "dendromatrix:unauthorized";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.detail;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "The archive could not complete the request.";
}

function unauthenticatedStatus(): AuthStatusSchema {
  return { requires_setup: false, authenticated: false, user: null };
}

/**
 * Owns the session status and the setup/login/logout mutations. The gate above
 * every archive route reads this context, so a lost cookie returns the reader
 * to the login screen without a page reload.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const statusQuery = useGetAuthStatus({
    query: {
      retry: false,
      staleTime: 30_000,
      refetchOnWindowFocus: true,
    },
  });

  const markSignedIn = useCallback(
    (user: UserSchema) => {
      queryClient.setQueryData<AuthStatusSchema>(getGetAuthStatusQueryKey(), {
        requires_setup: false,
        authenticated: true,
        user,
      });
      void queryClient.invalidateQueries();
    },
    [queryClient],
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
        queryClient.clear();
        queryClient.setQueryData<AuthStatusSchema>(
          getGetAuthStatusQueryKey(),
          unauthenticatedStatus(),
        );
      },
    },
  });

  useEffect(() => {
    const handleUnauthorized = () => {
      // Re-read the server state instead of assuming an owner exists. After a
      // first-run reset there is no owner, so the gate must show Setup again.
      void queryClient.invalidateQueries({
        queryKey: getGetAuthStatusQueryKey(),
      });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [queryClient]);

  const setup = useCallback(
    async (payload: SetupSchema) => {
      setError(null);
      try {
        await setupMutation.mutateAsync({ data: payload });
      } catch (caught) {
        setError(errorMessage(caught));
      }
    },
    [setupMutation],
  );

  const login = useCallback(
    async (payload: LoginSchema) => {
      setError(null);
      try {
        await loginMutation.mutateAsync({ data: payload });
      } catch (caught) {
        setError(errorMessage(caught));
      }
    },
    [loginMutation],
  );

  const logout = useCallback(async () => {
    setError(null);
    try {
      await logoutMutation.mutateAsync();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [logoutMutation]);

  const value = useMemo<AuthContextValue>(() => {
    const status = statusQuery.data;
    return {
      status,
      user: status?.user ?? null,
      isLoading: statusQuery.isPending,
      isAuthenticated: status?.authenticated ?? false,
      requiresSetup: status?.requires_setup ?? false,
      isSubmitting:
        setupMutation.isPending || loginMutation.isPending || logoutMutation.isPending,
      error,
      loadError: statusQuery.error ? errorMessage(statusQuery.error) : null,
      retry: () => {
        void statusQuery.refetch();
      },
      login,
      setup,
      logout,
    };
  }, [
    error,
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
