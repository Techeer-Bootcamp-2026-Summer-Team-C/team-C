import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "../api/endpoints";
import { configureApiAuth } from "../api/client";
import type { LoginRequest, UserDto } from "../contracts";

interface AuthValue {
  token: string | null;
  user: UserDto | null;
  login: (request: LoginRequest) => Promise<UserDto>;
  logout: (preserveIntended?: boolean) => void;
  preserveIntended: boolean;
}

interface AuthSession {
  token: string;
  user: UserDto;
  expiresAt: number;
}

const AUTH_SESSION_KEY = "edr.authSession";
const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<AuthSession | null>(initializeAuthSession);
  const [preserveIntended, setPreserveIntended] = useState(session === null);
  const token = session?.token ?? null;
  const user = session?.user ?? null;

  const logout = useCallback((keepIntended = false) => {
    setPreserveIntended(keepIntended);
    configureApiAuth(null, null);
    clearAuthSession();
    setSession(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    configureApiAuth(token, () => logout(true));
  }, [logout, token]);

  useEffect(() => {
    if (!session) return;
    const remainingMilliseconds = Math.max(0, session.expiresAt - Date.now());
    const timeout = window.setTimeout(() => logout(true), remainingMilliseconds);
    return () => window.clearTimeout(timeout);
  }, [logout, session]);

  const value = useMemo<AuthValue>(
    () => ({
      token,
      user,
      async login(request) {
        const response = await api.login(request);
        const nextSession = {
          token: response.data.accessToken,
          user: response.data.user,
          expiresAt: Date.now() + response.data.expiresIn * 1_000,
        };
        setPreserveIntended(false);
        configureApiAuth(nextSession.token, () => logout(true));
        saveAuthSession(nextSession);
        setSession(nextSession);
        return response.data.user;
      },
      logout,
      preserveIntended,
    }),
    [logout, preserveIntended, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function loadAuthSession(): AuthSession | null {
  try {
    const raw = window.sessionStorage.getItem(AUTH_SESSION_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!isAuthSession(value) || value.expiresAt <= Date.now()) {
      window.sessionStorage.removeItem(AUTH_SESSION_KEY);
      return null;
    }
    return value;
  } catch {
    clearAuthSession();
    return null;
  }
}

function initializeAuthSession(): AuthSession | null {
  const session = loadAuthSession();
  configureApiAuth(session?.token ?? null, null);
  return session;
}

function saveAuthSession(session: AuthSession): void {
  try {
    window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
  } catch {
    // A storage failure must not prevent login for the current page lifecycle.
  }
}

function clearAuthSession(): void {
  try {
    window.sessionStorage.removeItem(AUTH_SESSION_KEY);
  } catch {
    // The in-memory session is still cleared when browser storage is unavailable.
  }
}

function isAuthSession(value: unknown): value is AuthSession {
  if (!isRecord(value) || typeof value.token !== "string" || typeof value.expiresAt !== "number") return false;
  return isUserDto(value.user);
}

function isUserDto(value: unknown): value is UserDto {
  if (!isRecord(value)) return false;
  return (
    typeof value.userId === "number" &&
    typeof value.loginId === "string" &&
    typeof value.name === "string" &&
    ["ADMIN", "ANALYST", "VIEWER"].includes(String(value.role)) &&
    ["ACTIVE", "DISABLED"].includes(String(value.status))
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
  if (!auth.token || !auth.user) {
    return <Navigate replace state={auth.preserveIntended ? { intended } : null} to="/login" />;
  }
  return children;
}
