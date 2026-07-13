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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function loginData(email: string) {
  return {
    data: {
      accessToken: "memory-only",
      tokenType: "Bearer",
      expiresIn: 900,
      user: { userId: 1, email, name: "Analyst", role: "ANALYST", status: "ACTIVE" },
    },
    meta: { requestId: "req_login" },
  };
}

function mockAuthFetch(): ReturnType<typeof vi.fn> {
  return vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/auth/refresh")) {
      return Promise.resolve(
        jsonResponse(
          { error: { code: "INVALID_TOKEN", message: "No session", retryable: false, details: [] }, meta: { requestId: "req_refresh" } },
          401,
        ),
      );
    }
    if (url.includes("/auth/logout")) {
      return Promise.resolve(jsonResponse({ data: { loggedOut: true }, meta: { requestId: "req_logout" } }));
    }
    if (url.includes("/auth/login")) {
      return Promise.resolve(jsonResponse(loginData("analyst@example.com")));
    }
    return Promise.resolve(jsonResponse({ data: {}, meta: { requestId: "req_other" } }));
  });
}

it("guards a protected route, remembers it in memory, and returns after login", async () => {
  vi.stubGlobal("fetch", mockAuthFetch());
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
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/auth/refresh")) {
      return Promise.resolve(
        jsonResponse(
          { error: { code: "INVALID_TOKEN", message: "No session", retryable: false, details: [] }, meta: { requestId: "req_refresh" } },
          401,
        ),
      );
    }
    if (url.includes("/auth/logout")) {
      return Promise.resolve(jsonResponse({ data: { loggedOut: true }, meta: { requestId: "req_logout" } }));
    }
    return Promise.resolve(jsonResponse(loginData("admin@example.com")));
  });
  vi.stubGlobal("fetch", fetchMock);
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
