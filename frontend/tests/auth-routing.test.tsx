import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "../src/auth/AuthContext";
import { AppShell } from "../src/components/AppShell";
import { LoginPage } from "../src/pages/LoginPage";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

it("guards a protected route, remembers it in memory, and returns after login", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { accessToken: "memory-only", tokenType: "Bearer", expiresIn: 3600, user: { userId: 1, email: "analyst@example.com", name: "Analyst", role: "ANALYST", status: "ACTIVE" } }, meta: { requestId: "req_login" } }), { status: 200, headers: { "Content-Type": "application/json" } })));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><MemoryRouter initialEntries={["/alerts?status=OPEN"]}><Routes><Route path="/login" element={<LoginPage />} /><Route path="/alerts" element={<RequireAuth><h1>Alert destination</h1></RequireAuth>} /></Routes></MemoryRouter></AuthProvider></QueryClientProvider>);
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Email"), "analyst@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "test-password");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("heading", { name: "Alert destination" })).toBeInTheDocument();
  expect(localStorage.getItem("token")).toBeNull();
  expect(localStorage.getItem("user")).toBeNull();
});

it("does not retain the previous route after an explicit logout", async () => {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data: { accessToken: "memory-only", tokenType: "Bearer", expiresIn: 3600, user: { userId: 1, email: "admin@example.com", name: "Administrator", role: "ADMIN", status: "ACTIVE" } }, meta: { requestId: "req_login" } }), { status: 200, headers: { "Content-Type": "application/json" } }))));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><MemoryRouter initialEntries={["/alerts"]}><Routes><Route path="/login" element={<LoginPage />} /><Route element={<RequireAuth><AppShell /></RequireAuth>}><Route index element={<h1>Overview destination</h1>} /><Route path="alerts" element={<h1>Alert destination</h1>} /></Route></Routes></MemoryRouter></AuthProvider></QueryClientProvider>);

  for (const credentials of [1, 2]) {
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), `admin${credentials}@example.com`);
    await userEvent.type(screen.getByLabelText("Password"), "test-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    if (credentials === 1) {
      expect(await screen.findByRole("heading", { name: "Alert destination" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Log out" }));
    }
  }

  expect(await screen.findByRole("heading", { name: "Overview destination" })).toBeInTheDocument();
});
