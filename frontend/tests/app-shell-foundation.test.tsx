import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, RequireAuth } from "../src/auth/AuthContext";
import { AppShell } from "../src/components/AppShell";
import { LocaleProvider } from "../src/i18n/LocaleContext";

const USER = { userId: 1, loginId: "admin", name: "Administrator", role: "ADMIN", status: "ACTIVE", locale: "EN" } as const;

beforeEach(() => {
  sessionStorage.setItem("edr.authSession", JSON.stringify({ token: "shell-token", user: USER, expiresAt: Date.now() + 60_000 }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(success(USER)));
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("application shell foundation", () => {
  it("renders approved navigation groups, child hierarchy, and route breadcrumbs", async () => {
    renderShell();
    expect(await screen.findByRole("heading", { name: "Archive destination" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Triage" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Analysis" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Platform" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Archives" })).toHaveClass("nav-child", "active");

    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Operations" })).toHaveAttribute("href", "/operations");
    expect(within(breadcrumb).getByText("Archives")).toHaveAttribute("aria-current", "page");

    await userEvent.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(screen.getByRole("button", { name: "Compact navigation" })).toBeInTheDocument();
  });

  it("operates the mobile Drawer and account/report surfaces by keyboard", async () => {
    const user = userEvent.setup();
    renderShell();
    await screen.findByRole("heading", { name: "Archive destination" });

    const menuTrigger = screen.getByRole("button", { name: "Toggle navigation" });
    await user.click(menuTrigger);
    expect(screen.getByRole("dialog", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close navigation" })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(menuTrigger).toHaveFocus());

    const accountTrigger = screen.getByRole("button", { name: "Open account menu" });
    await user.click(accountTrigger);
    expect(screen.getByRole("dialog", { name: "Open account menu" })).toHaveTextContent("Administrator");
    expect(screen.getByText("ADMIN")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open printable report" }));
    expect(screen.getByRole("dialog", { name: "Archives snapshot" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close report" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Archives snapshot" })).not.toBeInTheDocument();
  });
});

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <LocaleProvider>
          <MemoryRouter initialEntries={["/operations/archives"]}>
            <Routes>
              <Route element={<RequireAuth><AppShell /></RequireAuth>}>
                <Route path="operations">
                  <Route index element={<h1>Operations destination</h1>} />
                  <Route path="archives" element={<h1>Archive destination</h1>} />
                </Route>
              </Route>
            </Routes>
          </MemoryRouter>
        </LocaleProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function success(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: { requestId: "req_shell" } }), { status: 200, headers: { "Content-Type": "application/json" } });
}
