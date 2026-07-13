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

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserDto | null>(null);
  const [preserveIntended, setPreserveIntended] = useState(true);

  const logout = useCallback((keepIntended = false) => {
    setPreserveIntended(keepIntended);
    setToken(null);
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    configureApiAuth(token, () => logout(true));
    return () => configureApiAuth(null, null);
  }, [logout, token]);

  const value = useMemo<AuthValue>(
    () => ({
      token,
      user,
      async login(request) {
        const response = await api.login(request);
        setPreserveIntended(false);
        setToken(response.data.accessToken);
        setUser(response.data.user);
        return response.data.user;
      },
      logout,
      preserveIntended,
    }),
    [logout, preserveIntended, token, user],
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
  if (!auth.token || !auth.user) {
    return <Navigate replace state={auth.preserveIntended ? { intended } : null} to="/login" />;
  }
  return children;
}
