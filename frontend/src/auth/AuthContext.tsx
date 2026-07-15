import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "../api/endpoints";
import { configureApiAuth } from "../api/client";
import type { LoginRequest, UserDto, UserLocale } from "../contracts";

interface AuthValue {
  token: string | null;
  user: UserDto | null;
  login: (request: LoginRequest) => Promise<UserDto>;
  updateLocale: (locale: UserLocale) => Promise<UserDto>;
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
  const localeUpdateVersion = useRef(0);
  const [session, setSession] = useState<AuthSession | null>(initializeAuthSession);
  const [preserveIntended, setPreserveIntended] = useState(session === null);
  const token = session?.token ?? null;
  const user = session?.user ?? null;

  const logout = useCallback((keepIntended = false) => {
    localeUpdateVersion.current += 1;
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
    if (!token) return;
    let active = true;
    const syncVersion = localeUpdateVersion.current;
    void api.currentUser().then((response) => {
      if (!active || localeUpdateVersion.current !== syncVersion) return;
      setSession((current) => {
        if (!current || current.token !== token) return current;
        const nextSession = { ...current, user: response.data };
        saveAuthSession(nextSession);
        return nextSession;
      });
    }).catch(() => {
      // 401 is handled by the configured auth callback. Temporary failures keep the restored session.
    });
    return () => { active = false; };
  }, [token]);

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
        localeUpdateVersion.current += 1;
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
      async updateLocale(locale) {
        if (!session) throw new Error("An authenticated session is required.");
        if (session.user.locale === locale) return session.user;
        const requestToken = session.token;
        const updateVersion = ++localeUpdateVersion.current;
        const response = await api.updateLocale({ locale });
        setSession((current) => {
          if (
            !current ||
            current.token !== requestToken ||
            localeUpdateVersion.current !== updateVersion
          ) return current;
          const nextSession = { ...current, user: response.data };
          saveAuthSession(nextSession);
          return nextSession;
        });
        return response.data;
      },
      logout,
      preserveIntended,
    }),
    [logout, preserveIntended, session, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function loadAuthSession(): AuthSession | null {
  try {
    const raw = window.sessionStorage.getItem(AUTH_SESSION_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    const normalized = normalizeAuthSession(value);
    if (!normalized || normalized.expiresAt <= Date.now()) {
      window.sessionStorage.removeItem(AUTH_SESSION_KEY);
      return null;
    }
    if (!isAuthSession(value)) saveAuthSession(normalized);
    return normalized;
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
  return hasUserDtoFields(value) && isUserLocale(value.locale);
}

function hasUserDtoFields(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) return false;
  return (
    typeof value.userId === "number" &&
    typeof value.loginId === "string" &&
    typeof value.name === "string" &&
    ["ADMIN", "ANALYST", "VIEWER"].includes(String(value.role)) &&
    ["ACTIVE", "DISABLED"].includes(String(value.status))
  );
}

function normalizeAuthSession(value: unknown): AuthSession | null {
  if (!isRecord(value) || typeof value.token !== "string" || typeof value.expiresAt !== "number") return null;
  const user = normalizeUserDto(value.user);
  return user ? { token: value.token, expiresAt: value.expiresAt, user } : null;
}

function normalizeUserDto(value: unknown): UserDto | null {
  if (!hasUserDtoFields(value)) return null;
  const locale: UserLocale = isUserLocale(value.locale) ? value.locale : "EN";
  return {
    userId: Number(value.userId),
    loginId: String(value.loginId),
    name: String(value.name),
    role: value.role as UserDto["role"],
    status: value.status as UserDto["status"],
    locale,
  };
}

function isUserLocale(value: unknown): value is UserLocale {
  return value === "EN" || value === "KO";
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
