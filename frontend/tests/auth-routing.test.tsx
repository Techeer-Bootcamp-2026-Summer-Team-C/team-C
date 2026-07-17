import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "../src/auth/AuthContext";
import { apiRequest } from "../src/api/client";
import { AppShell } from "../src/components/AppShell";
import { LocaleProvider } from "../src/i18n/LocaleContext";
import { LoginPage } from "../src/pages/LoginPage";
import { ThemeProvider } from "../src/theme/ThemeProvider";

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

it("guards a protected route, returns after login, and restores the session after a reload", async () => {
  const user = { userId: 1, loginId: "analyst", name: "Analyst", role: "ANALYST", status: "ACTIVE", locale: "EN" };
  vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const path = String(input);
    const data = path.endsWith("/auth/login")
      ? { accessToken: "session-token", tokenType: "Bearer", expiresIn: 43200, user }
      : path.endsWith("/users/me") ? user : {};
    return Promise.resolve(new Response(JSON.stringify({ data, meta: { requestId: "req_auth" } }), { status: 200, headers: { "Content-Type": "application/json" } }));
  }));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><MemoryRouter initialEntries={["/alerts?status=OPEN"]}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/alerts" element={<RequireAuth><h1>Alert destination</h1></RequireAuth>} /></Routes></MemoryRouter></AuthProvider></ThemeProvider></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Login ID"), "analyst");
  await userEvent.type(screen.getByLabelText("Password"), "test-password");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("heading", { name: "Alert destination" })).toBeInTheDocument();
  expect(localStorage.getItem("token")).toBeNull();
  expect(localStorage.getItem("user")).toBeNull();
  expect(sessionStorage.getItem("edr.authSession")).toContain("session-token");

  cleanup();
  const reloadedQueryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={reloadedQueryClient}><ThemeProvider><AuthProvider><MemoryRouter initialEntries={["/alerts"]}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/alerts" element={<RequireAuth><ReloadProbe /></RequireAuth>} /></Routes></MemoryRouter></AuthProvider></ThemeProvider></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Restored destination" })).toBeInTheDocument();
  const reloadCall = vi.mocked(fetch).mock.calls.find(([input]) => String(input).endsWith("/reload-probe"));
  expect(reloadCall).toBeDefined();
  const request = reloadCall?.[1];
  expect(new Headers(request?.headers).get("Authorization")).toBe("Bearer session-token");
});

it("does not retain the previous route after an explicit logout", async () => {
  const user = { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" };
  vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify({ data: String(input).endsWith("/users/me") ? user : { accessToken: "memory-only", tokenType: "Bearer", expiresIn: 43200, user }, meta: { requestId: "req_login" } }), { status: 200, headers: { "Content-Type": "application/json" } }))));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><LocaleProvider><MemoryRouter initialEntries={["/alerts"]}><Routes><Route path="/login" element={<LoginPage />} /><Route element={<RequireAuth><AppShell /></RequireAuth>}><Route index element={<h1>Overview destination</h1>} /><Route path="alerts" element={<h1>Alert destination</h1>} /></Route></Routes></MemoryRouter></LocaleProvider></AuthProvider></ThemeProvider></QueryClientProvider>);

  for (const credentials of [1, 2]) {
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Login ID"), `admin${credentials}`);
    await userEvent.type(screen.getByLabelText("Password"), "test-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    if (credentials === 1) {
      expect(await screen.findByRole("heading", { name: "Alert destination" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Open account menu" }));
      await userEvent.click(screen.getByRole("button", { name: "Log out" }));
      expect(sessionStorage.getItem("edr.authSession")).toBeNull();
    }
  }

  expect(await screen.findByRole("heading", { name: "Overview destination" })).toBeInTheDocument();
});

it("removes a malformed stored session before showing login", async () => {
  sessionStorage.setItem("edr.authSession", "{not-json");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(<QueryClientProvider client={queryClient}><ThemeProvider><AuthProvider><MemoryRouter initialEntries={["/alerts"]}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/alerts" element={<RequireAuth><h1>Alert destination</h1></RequireAuth>} /></Routes></MemoryRouter></AuthProvider></ThemeProvider></QueryClientProvider>);

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  expect(sessionStorage.getItem("edr.authSession")).toBeNull();
});

function ReloadProbe() {
  useEffect(() => {
    void apiRequest<Record<string, never>>("/reload-probe");
  }, []);
  return <h1>Restored destination</h1>;
}
