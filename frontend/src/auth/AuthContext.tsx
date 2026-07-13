import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "../api/endpoints";
import { configureApiAuth, configureApiRefresh } from "../api/client";
import type { LoginRequest, UserDto } from "../contracts";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthValue {
  status: AuthStatus;
  token: string | null;
  user: UserDto | null;
  login: (request: LoginRequest) => Promise<UserDto>;
  logout: (preserveIntended?: boolean) => void;
  preserveIntended: boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserDto | null>(null);
  const [preserveIntended, setPreserveIntended] = useState(true);

  const clearLocalSession = useCallback(
    (keepIntended = false) => {
      setPreserveIntended(keepIntended);
      setToken(null);
      setUser(null);
      setStatus("anonymous");
      queryClient.clear();
    },
    [queryClient],
  );

  useEffect(() => {
    configureApiAuth(token, () => clearLocalSession(true));
    return () => configureApiAuth(null, null);
  }, [clearLocalSession, token]);

  useEffect(() => {
    configureApiRefresh(async () => {
      try {
        const response = await api.refresh();
        setToken(response.data.accessToken);
        setUser(response.data.user);
        setStatus("authenticated");
        return true;
      } catch {
        return false;
      }
    });
    return () => configureApiRefresh(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .refresh()
      .then((response) => {
        if (cancelled) return;
        setToken(response.data.accessToken);
        setUser(response.data.user);
        setStatus("authenticated");
      })
      .catch(() => {
        if (!cancelled) setStatus("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      status,
      token,
      user,
      async login(request) {
        const response = await api.login(request);
        setPreserveIntended(false);
        setToken(response.data.accessToken);
        setUser(response.data.user);
        setStatus("authenticated");
        return response.data.user;
      },
      logout(keepIntended = false) {
        void api
          .logout()
          .catch(() => undefined)
          .finally(() => clearLocalSession(keepIntended));
      },
      preserveIntended,
    }),
    [clearLocalSession, preserveIntended, status, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  const intended = `${location.pathname}${location.search}`;
  if (auth.status === "loading") {
    return (
      <main className="auth-loading" aria-live="polite">
        Checking your session…
      </main>
    );
  }
  if (auth.status !== "authenticated" || !auth.token || !auth.user) {
    return <Navigate replace state={auth.preserveIntended ? { intended } : null} to="/login" />;
  }
  return children;
}
